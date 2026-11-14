"""The smallest layer that makes a base answer an oracle's questions as the old names table does.

`minimal_layer(legacy, below, rows)` takes the old table compiled (`verso.ru.naming.legacy`), the layers it is to
stand on (the base) and the oracle's questions (`verso.ru.naming.oracle`), and chooses entries of the old table
for a layer above them:

 0. Beside the oracle's questions, `derived_questions`: the woman's fold of every patronymic it names
    (`feminine_patronymic`), which no oracle records and a consolidation check compares patronymics by.
 1. Every question is asked of the old table alone (the target) and of the sum — the layers below, then the
    chosen entries. Where the two answer otherwise, the entries of the old table are taken for each key either
    lookup asked (`names_registry.asked`):
      * a name (`name`, `ignore_name`) — its entries of every sex, unsexed too, and its forms;
      * a short or modern patronymic, a genitive — the entries the old table's answer stands on
        (`Lexicon.explain`): its pin, or the names whose forms give it, each taken as a name;
      * a patronymic of the old ignore list — its entry.
 2. A base an entry folds onto that no layer holds is taken too, as a name (LEX003 would refuse the layer).
 3. A question still answered otherwise once its keys' entries are all taken gets the old table's answer written
    down: a pin for each short or modern patronymic it asked, a father's forms cell for a patronymic the old
    table gave by another way (`derive_patronymic`, `derive_old_patronymic`), and «no such form» (`-`) in a
    forms cell the old table left empty where the rules would fill it — a form the old table does not know.
 4. A question nothing of the old table settles, where the layers below hold a name in a sex the old table does
    not: a names row removing that (sex, name) from the stack (`ABSENT`, `-` in bases) — only there.
 4a. Two names giving one key in the sum (`LexiconConflict`) gets a pin of the old table's answer to that key.
 5. Once every question agrees, the entries the layers below may answer alike (a name entry they hold alike, a
    forms entry whose forms they give alike, any pin) are left out at once, and each one a question then
    answered otherwise rests on is put back — until none does.

Repeated until every question agrees, or no entry is left to take — then the questions that still differ are
the error (`LayerDiffError`, the entries chosen so far beside them). A name is preferred to a pin where both
would do: the name's entry answers its other questions too, the pin is the exception kept for what the forms do
not give. A forms cell the rules give alike is left empty, and a forms entry left empty is not written — the
layer derives (`Layer.derives`) — unless it replaces one of a layer below, which an empty entry does whole.

What no entry settles: a question whose answer the layers below give and the old table's entries cannot
replace, a removal included.

Every entry chosen is written with the source `legacy` — but a name of the old ignore list, whose source
(`IGNORE_LIST`, «ignore») is what `is_ignored_name` answers by and keeps.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from verso.ru.gender import Gender
from verso.ru.messages import t
from verso.ru.naming import oracle
from verso.ru.naming.derived import fill
from verso.ru.naming.layer_files import FILES, KEY_COLUMN, Table, row_of, sort_key, write_table
from verso.ru.naming.lexicon import (
    ABSENT, IGNORE_LIST, FormsEntry, Layer, Lexicon, LexiconConflict, NameEntry, PatronymicEntry)

#: The source of every entry `minimal_layer` writes (but the ignore list's names).
SOURCE = "legacy"

Entry = NameEntry | FormsEntry | PatronymicEntry
Key = tuple[Table, tuple[Gender | None, str]]
#: Why an entry was taken: one of a differing question's own keys, in the first round; a base an entry folds
#: onto; a key of a later round; a pin of a question its keys did not settle; a pin of a conflict.
Reason = Literal["question", "base", "round", "pin", "conflict", "removal"]
#: The forms cells a father's patronymic is read from, the son's and the daughter's.
_CELLS = {"derive_patronymic": ("patronymic_m", "patronymic_f"),
          "derive_old_patronymic": ("old_patronymic_m", "old_patronymic_f")}
#: The forms cell a reverse key is derived from.
_NONE_CELL = {"old_m": "old_patronymic_m", "old_f": "old_patronymic_f", "modern_m": "patronymic_m",
              "modern_f": "patronymic_f", "genitive": "genitive"}
_REVERSE_SEX = {"old_m": Gender.MALE, "old_f": Gender.FEMALE, "modern_m": Gender.MALE, "modern_f": Gender.FEMALE}


class LayerDiffError(Exception):
    """Questions no entry of the old table makes the sum answer as the old table does."""

    def __init__(self, rows: Sequence[tuple[oracle.Row, Any, Any]], result: Result) -> None:
        self.rows = tuple(rows)
        self.result = result
        lines = [f"{r.function} {oracle.dumps(list(r.args))}: {oracle.dumps(want)} ≠ {oracle.dumps(got)}"
                 for r, want, got in self.rows]
        super().__init__(str(t("layer_diff.unresolved", count=len(self.rows), rows="\n".join(lines))))


class LayerDiffConflict(Exception):
    """Two names the sum derives one key from, which the old table answers with nothing to pin: the layer cannot be
    summed — the conflict's key and candidates said."""

    def __init__(self, conflict: LexiconConflict) -> None:
        self.conflict = conflict
        index, key = conflict.key
        super().__init__(str(t("layer_diff.conflict", index=index, key=key,
                               candidates=", ".join(map(str, conflict.candidates)))))


@dataclass
class Result:
    """The entries chosen, by table and key, why each was taken, and how the choosing went."""
    entries: dict[Key, Entry] = field(default_factory=dict[Key, Entry])
    reasons: dict[Key, Reason] = field(default_factory=dict[Key, Reason])
    rounds: int = 0
    differing: int = 0      # questions the layers below answered otherwise than the old table
    derived: int = 0        # questions asked beside the oracle's (`derived_questions`)
    stale: int = 0          # questions whose recorded answer is not the old table's today

    def layer(self, name: str = "layer-diff") -> Layer:
        """The entries as a deriving layer — what the files `write()` writes read back as."""
        tables: dict[Table, dict[Any, Any]] = {"names": {}, "forms": {}, "patronymics": {}}
        for (table, key), entry in self.entries.items():
            tables[table][key] = entry
        return Layer(name, tables["names"], tables["forms"], tables["patronymics"], derives=True)

    def counts(self) -> dict[Table, int]:
        out: dict[Table, int] = {"names": 0, "forms": 0, "patronymics": 0}
        for table, _ in self.entries:
            out[table] += 1
        return out


def _relabel(entry: Entry) -> Entry:
    if isinstance(entry, NameEntry) and entry.source == IGNORE_LIST:
        return entry
    return entry._replace(source=SOURCE)


def _lean_forms(entry: FormsEntry, shadows: bool) -> FormsEntry | None:
    """The forms entry with every cell the rules give alike left empty; None when none is left and the entry
    `shadows` no forms entry of a layer below — an upper entry replaces the lower one whole, so an empty one
    there says «the rules', not the layer's below»."""
    rule = fill(None, entry.sex, entry.name)
    cells = [None if cell == ruled else cell for cell, ruled in zip(entry[2:7], rule[2:7], strict=True)]
    if not any(cells) and not shadows:
        return None
    return FormsEntry(entry.sex, entry.name, *cells, source=SOURCE)


class _Chooser:
    def __init__(self, legacy: Layer, below: Sequence[Layer]) -> None:
        self.legacy = legacy
        self.target = Lexicon.of([legacy]).complete()
        self.below = tuple(below)
        self.below_names = {name for layer in below for _, name in layer.names}
        self.below_forms: dict[tuple[Gender, str], FormsEntry] = {}
        self.below_names_sum: dict[tuple[Gender | None, str], NameEntry] = {}
        for layer in below:
            self.below_forms.update(layer.forms)
            self.below_names_sum.update(layer.names)
        self.keys_of_name: dict[str, list[Key]] = {}
        for key in legacy.names:
            self.keys_of_name.setdefault(key[1], []).append(("names", key))
        for key in legacy.forms:
            self.keys_of_name.setdefault(key[1], []).append(("forms", key))
        self.result = Result()
        self.taken_names: set[str] = set()

    # --- taking entries ---

    def _put(self, key: Key, entry: Entry | None, reason: Reason) -> bool:
        if key in self.result.entries or key in self.result.reasons:
            return False
        self.result.reasons[key] = reason
        if entry is not None:
            self.result.entries[key] = entry
        return True

    def take_name(self, name: str, reason: Reason) -> bool:
        """The old table's entries of `name`, and of each base they fold onto that no layer holds."""
        if name in self.taken_names:
            return False
        self.taken_names.add(name)
        new = False
        for table, key in self.keys_of_name.get(name, ()):
            if table == "names":
                entry: Entry | None = _relabel(self.legacy.names[key])
            else:
                entry = _lean_forms(self.legacy.forms[key], key in self.below_forms)  # type: ignore[index]
            new = self._put((table, key), entry, reason) or new
        for table, key in self.keys_of_name.get(name, ()):
            if table == "names":
                for base in self.legacy.names[key].bases:
                    if base not in self.below_names and base not in self.taken_names and base in self.keys_of_name:
                        new = self.take_name(base, "base") or new
        return new

    def take_key(self, kind: str, key: str, reason: Reason) -> bool:
        """The old table's entries a lookup of `kind` by `key` answers by."""
        if kind in ("name", "ignore_name"):
            return self.take_name(key, reason)
        if kind == "ignore_patronymic":
            entry = self.legacy.patronymics.get((None, key))
            return entry is not None and self._put(("patronymics", (None, key)), _relabel(entry), reason)
        new = False
        for _, entry in self.target.explain(kind, key):
            if isinstance(entry, PatronymicEntry):
                new = self._put(("patronymics", entry.key), _relabel(entry), reason) or new
            else:
                new = self.take_name(entry.name, reason) or new
        return new

    def pin(self, kind: str, key: str, reason: Reason) -> bool:
        """The old table's answer to a short or modern patronymic `key`, written down as a pin."""
        sex = _REVERSE_SEX.get(kind)
        if sex is None:
            return False
        if kind.startswith("old"):
            found = (self.target.old_m if sex is Gender.MALE else self.target.old_f).get(key)
            entry = None if found is None else PatronymicEntry(sex, key, found.father, found.modern, SOURCE)
        else:
            short = (self.target.modern_m if sex is Gender.MALE else self.target.modern_f).get(key)
            entry = None if short is None else PatronymicEntry(sex, key, source=SOURCE, old=short)
        if entry is None:
            return False
        held = self.result.entries.get(("patronymics", (sex, key)))
        if held == entry:
            return False
        self.result.entries[("patronymics", (sex, key))] = entry
        self.result.reasons.setdefault(("patronymics", (sex, key)), reason)
        return True

    def _forms_entry(self, key: tuple[Gender, str]) -> FormsEntry:
        """This layer's forms entry of `key` as it stands, else the old table's (lean), else an empty one."""
        held = self.result.entries.get(("forms", key))
        if isinstance(held, FormsEntry):
            return held
        legacy = self.legacy.forms.get(key)
        lean = _lean_forms(legacy, True) if legacy is not None else None
        return lean or FormsEntry(key[0], key[1], source=SOURCE)

    def write_none(self, row: oracle.Row, answer: Any, keys: Iterable[tuple[str, str]], current: Lexicon) -> bool:
        """«No such form» (`NO_FORM`, "" in the entry) in a forms cell the old table left empty and the rules fill: for
        a reverse key the old table does not know and the sum does, in the old table's names whose rule-filled forms
        give it; for a father's short patronymic the old table answers with nothing."""
        new = False
        for kind, key in keys:
            column = _NONE_CELL.get(kind)
            if column is None or key in getattr(self.target, kind):
                continue
            for _, entry in current.explain(kind, key):
                if isinstance(entry, FormsEntry) and entry.key in self.legacy.names:
                    new = self._set_none(entry.key, column) or new
        if row.function == "derive_old_patronymic" and answer == "":
            name, child = row.args
            sex = Gender.MALE if (Gender.MALE, name) in self.legacy.names else Gender.FEMALE
            if (sex, name) in self.legacy.names:
                new = self._set_none((sex, name), "old_patronymic_m" if child == "M" else "old_patronymic_f") or new
        return new

    def write_removal(self, keys: Iterable[tuple[str, str]], current: Lexicon) -> bool:
        """A names row removing (`ABSENT`) a (sex, name) the layers below hold and the old table does not — for the
        name a question was asked of, when nothing else settled it."""
        new = False
        for kind, name in keys:
            if kind not in ("name", "ignore_name"):
                continue
            facts = current.by_name.get(name)
            for sex, held in ((Gender.MALE, facts.male if facts else None), (Gender.FEMALE, facts.female if facts else None)):
                key = ("names", (sex, name))
                if held is None or (sex, name) in self.legacy.names or key in self.result.entries:
                    continue
                self.result.entries[key] = NameEntry(sex, name, (ABSENT,), source=SOURCE)
                self.result.reasons.setdefault(key, "removal")
                new = True
        return new

    def _set_none(self, key: tuple[Gender, str], column: str) -> bool:
        legacy = self.legacy.forms.get(key)
        if legacy is not None and getattr(legacy, column) is not None:
            return False  # the old table writes a form there: not «none»
        held = self._forms_entry(key)
        if getattr(held, column) == "":
            return False
        self.result.entries[("forms", key)] = held._replace(**{column: "", "source": SOURCE})
        self.result.reasons.setdefault(("forms", key), "pin")
        return True

    def write_cell(self, row: oracle.Row, answer: Any) -> bool:
        """The old table's answer to a father's patronymic (`derive_patronymic`, `derive_old_patronymic`), written into
        the father's forms where the old table left the cell empty and answered by another way (the short form of
        its modern patronymic): an empty cell of this layer is the rule's."""
        cells = _CELLS.get(row.function)
        if cells is None or not isinstance(answer, str) or not answer:
            return False
        name, child = row.args
        sex = Gender.MALE if (Gender.MALE, name) in self.legacy.names or (Gender.MALE, name) in self.legacy.forms \
            else Gender.FEMALE
        key = ("forms", (sex, name))
        held = self.result.entries.get(key) or self.below_forms.get((sex, name)) or FormsEntry(sex, name)
        assert isinstance(held, FormsEntry)
        cell = cells[0] if child == "M" else cells[1]
        value = None if getattr(fill(None, sex, name), cell) == answer else answer  # the rule's: left empty
        if key in self.result.entries and getattr(held, cell) == value:
            return False
        self.result.entries[key] = held._replace(**{cell: value, "source": SOURCE})
        self.result.reasons.setdefault(key, "pin")
        return True

    # --- leaving out what the layers below answer alike ---

    def redundant(self, key: Key) -> bool:
        """Whether the entry of `key` may answer as the layers below do: a name entry they hold alike, a forms entry
        whose forms (the rules' where a cell is empty) they give alike, any pin — the questions decide."""
        table, k = key
        entry = self.result.entries[key]
        if table == "names":
            held = self.below_names_sum.get(k)
            return held is not None and isinstance(entry, NameEntry) and (
                held.bases, held.canonical, held.source == IGNORE_LIST) == (
                entry.bases, entry.canonical, entry.source == IGNORE_LIST)
        if table == "forms":
            assert isinstance(entry, FormsEntry)
            held_forms = self.below_forms.get(entry.key)
            return fill(entry, entry.sex, entry.name)[2:7] == fill(held_forms, entry.sex, entry.name)[2:7]
        return True

    def related(self, keys: frozenset[tuple[str, str]]) -> set[Key]:
        """The entries' keys a question looked up by `keys` may rest on."""
        names: set[str] = set()
        out: set[Key] = set()
        for kind, key in keys:
            if kind in ("name", "ignore_name"):
                names.add(key)
            elif kind == "ignore_patronymic":
                out.add(("patronymics", (None, key)))
            else:
                if kind in _REVERSE_SEX:        # a genitive is no pin: only the names whose forms give it
                    out.add(("patronymics", (_REVERSE_SEX[kind], key)))
                names.update(entry.name for _, entry in self.target.explain(kind, key)
                             if not isinstance(entry, PatronymicEntry))
        for name in names:
            for sex in (Gender.MALE, Gender.FEMALE, None):
                out.add(("names", (sex, name)))
                if sex is not None:
                    out.add(("forms", (sex, name)))
        return out

    # --- asking ---

    def sum(self) -> Lexicon:
        """The layers below and the entries chosen, complete — each conflict pinned as the old table answers."""
        while True:
            try:
                return Lexicon.of([*self.below, self.result.layer()]).complete()
            except LexiconConflict as conflict:
                kind, key = conflict.key
                if not self.pin(kind, key, "conflict"):
                    raise LayerDiffConflict(conflict) from None


#: The oracle's functions whose first argument is a patronymic: each such patronymic is asked `feminine_patronymic`
#: too, the fold a consolidation check compares two patronymics by — no oracle records it.
_PATRONYMIC_QUESTIONS = frozenset({"canonicalize_patronymic", "validate_old_patronymic", "father_name_for_patronymic",
                                   "get_gender_from_old_patronymic", "is_ignored_patronymic",
                                   "find_old_patronymic_by_modern"})


def derived_questions(rows: Sequence[oracle.Row]) -> list[oracle.Row]:
    """The questions `minimal_layer` asks beside the oracle's: `feminine_patronymic` of every patronymic it names."""
    asked = {r.args[0] for r in rows if r.function in _PATRONYMIC_QUESTIONS and isinstance(r.args[0], str)}
    return [oracle.Row("feminine_patronymic", (p,), None) for p in sorted(asked)]


def minimal_layer(legacy: Layer, below: Sequence[Layer], rows: Sequence[oracle.Row]) -> Result:
    """The entries of `legacy` a layer above `below` needs to answer every one of `rows` as `legacy` alone does
    (see the module's docstring). `LayerDiffError` — with the entries chosen so far — when questions are left
    that no entry settles."""
    chooser = _Chooser(legacy, below)
    recorded = oracle.answers(rows, chooser.target)
    chooser.result.stale = sum(not oracle.same(w.answer, r.answer) for w, r in zip(recorded, rows, strict=True))
    extra = derived_questions(rows)
    chooser.result.derived = len(extra)
    rows = [*rows, *extra]
    want = [*recorded, *oracle.answers(extra, chooser.target)]
    first = True
    while True:
        current = chooser.sum()
        got = oracle.answers(rows, current)
        differing = [i for i, (w, g) in enumerate(zip(want, got, strict=True)) if not oracle.same(w.answer, g.answer)]
        if first:
            chooser.result.differing = len(differing)
        if not differing:
            _prune(chooser, rows, want, set())
            return chooser.result
        chooser.result.rounds += 1
        new = False
        for i in differing:
            keys = sorted(want[i].keys | got[i].keys)
            took = [chooser.take_key(kind, key, "question" if first else "round") for kind, key in keys]
            if not any(took):
                # Its keys' entries are all taken: the old table's answer, written down.
                took = [chooser.pin(kind, key, "pin") for kind, key in keys]
                took.append(chooser.write_cell(rows[i], want[i].answer))
                took.append(chooser.write_none(rows[i], want[i].answer, keys, current))
            if not any(took):
                # Nothing of the old table settles it: a name the layers below hold in a sex the old table does not
                # is removed from the stack.
                asked = rows[i].args[0] if rows[i].args else None
                took = [chooser.write_removal([(k, n) for k, n in keys if n == asked], current)]
            new = new or any(took)
        first = False
        if not new:
            _prune(chooser, rows, want, set(differing))
            raise LayerDiffError([(rows[i], want[i].answer, got[i].answer) for i in differing], chooser.result)


def _prune(chooser: _Chooser, rows: Sequence[oracle.Row], want: Sequence[oracle.Asked], left: set[int]) -> None:
    """Leave out every entry the questions do not need: all that may answer as the layers below (`redundant`) at
    once, then back each one a question answered otherwise rests on (`related`) — or a conflict names — until the
    questions answered otherwise are `left` alone; then the entries put back as a group, one at a time (`_trim`).
    An entry put back and needed stays."""
    entries, kept, restored = chooser.result.entries, set[Key](), set[Key]()
    while True:
        out = {key: entries.pop(key) for key in sorted(entries, key=repr) if key not in kept and chooser.redundant(key)}
        if not out:
            return
        while out:
            try:
                lexicon = Lexicon.of([*chooser.below, chooser.result.layer()]).complete()
            except LexiconConflict as conflict:
                kind, key = conflict.key
                back = {k for k in out if k == ("patronymics", (_REVERSE_SEX[kind], key))} or set(out)
            else:
                got = oracle.answers(rows, lexicon)
                bad = [i for i, (w, g) in enumerate(zip(want, got, strict=True))
                       if i not in left and not oracle.same(w.answer, g.answer)]
                if not bad:
                    break
                wanted = set().union(*(chooser.related(want[i].keys | got[i].keys) for i in bad))
                back = {k for k in out if k in wanted} or set(out)
            for key in back:
                entries[key] = out.pop(key)
                kept.add(key)
                restored.add(key)
        _trim(chooser, rows, want, left, restored)
        restored = set()


def _touches(keys: frozenset[tuple[str, str]]) -> set[Key]:
    """The entries a question looked up by `keys` reads first-hand: its names' entries and forms, the pins of its
    patronymic keys (`_Chooser.related` reads the old table's derivations too, and costs more)."""
    out: set[Key] = set()
    for kind, key in keys:
        if kind in ("name", "ignore_name"):
            for sex in (Gender.MALE, Gender.FEMALE, None):
                out.add(("names", (sex, key)))
                if sex is not None:
                    out.add(("forms", (sex, key)))
        elif kind == "ignore_patronymic":
            out.add(("patronymics", (None, key)))
        elif kind in _REVERSE_SEX:      # a genitive is read from a name's forms, which its names' entries cover
            out.add(("patronymics", (_REVERSE_SEX[kind], key)))
    return out


def _trim(chooser: _Chooser, rows: Sequence[oracle.Row], want: Sequence[oracle.Asked], left: set[int],
          restored: set[Key]) -> None:
    """The entries put back as a group, left out one at a time: each one whose questions — those that read it
    first-hand — still answer as the old table without it goes. A full replay checks the whole; what it finds answered
    otherwise puts back the entries its questions read (all those left out, when none)."""
    entries = chooser.result.entries

    def summed() -> Lexicon | None:
        try:
            return Lexicon.of([*chooser.below, chooser.result.layer()]).complete()
        except LexiconConflict:
            return None

    lexicon = summed()
    if lexicon is None or not restored:
        return
    got = oracle.answers(rows, lexicon)
    reading: dict[Key, list[int]] = {}
    for i, (w, g) in enumerate(zip(want, got, strict=True)):
        for key in _touches(w.keys | g.keys):
            reading.setdefault(key, []).append(i)
    gone: dict[Key, Entry] = {}
    for key in sorted(restored, key=repr):
        entry = entries.pop(key)
        # Unchecked — a collision this one leaves answers by a fixed order here, and the full check below refuses it.
        lexicon = Lexicon.of([*chooser.below, chooser.result.layer()])
        asked = reading.get(key, [])
        if all(
                i in left or oracle.same(want[i].answer, a.answer)
                for i, a in zip(asked, oracle.answers([rows[i] for i in asked], lexicon), strict=True)):
            gone[key] = entry
        else:
            entries[key] = entry
    while gone:
        try:
            lexicon = Lexicon.of([*chooser.below, chooser.result.layer()]).complete()
        except LexiconConflict as conflict:  # a pin left out settled it: that pin back, else all
            kind, form = conflict.key
            pin = ("patronymics", (_REVERSE_SEX[kind], form))
            for key in [pin] if pin in gone else list(gone):
                entries[key] = gone.pop(key)
            continue
        got = oracle.answers(rows, lexicon)
        bad = [i for i, (w, g) in enumerate(zip(want, got, strict=True))
               if i not in left and not oracle.same(w.answer, g.answer)]
        if not bad:
            return
        wanted = set().union(*(_touches(want[i].keys | got[i].keys) | chooser.related(want[i].keys | got[i].keys)
                               for i in bad))
        back = {k for k in gone if k in wanted} or set(gone)
        for key in back:
            entries[key] = gone.pop(key)


def write(result: Result, directory: Path) -> None:
    """The entries as a layer's three files (`verso.ru.naming.layer_files`), each sorted by its key: the same entries
    write the same bytes."""
    by_table: dict[Table, list[dict[str, str]]] = {table: [] for table in FILES}
    for entry in result.entries.values():
        table, row = row_of(entry)
        by_table[table].append(row)
    for table, rows in by_table.items():
        column = KEY_COLUMN[table]
        write_table(directory, table, sorted(rows, key=lambda r, c=column: sort_key(r["sex"], r[c])))
