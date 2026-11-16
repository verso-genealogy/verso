"""Add, remove, check and explain a name in the names layers; `layer-diff` writes a layer from the old tables.

    verso names add --gender Ж --name Евфрасиния --base Ефросиния --genitive Евфрасинии --source "Горюхино 1917"
    verso names remove --gender Ж --name Евфрасиния
    verso names pin --gender М --form Зюзеин --father Зюзей --modern Зюзеевич --source "Горюхино МК 1901"
    verso names unpin --gender М --form Зюзеин
    verso names check [--layer DIR | --all]
    verso names explain Евфрасиния [--gender Ж]

A workspace of schema 6 keeps its names in layers over the base the library ships (`[names]`, `verso.ru.naming.layers`).
`add` writes one row to a key into the writable layer (`--layer DIR` another of the workspace's layers) — a row has no
place and no order: the key is unique and the layer's files are kept sorted by it. The row is read first by the layers'
linter (`verso.ru.linters.checks.lexicon`) over the layers under it; a hard finding (LEX001 a key no lookup can ask by,
LEX003 a base no layer holds, LEX007 two derivations of one patronymic) refuses it and writes nothing, and a row that
answers as the sum without it does (LEX005) is written with the warning saying so. `remove` deletes the layer's rows of the
key; for a name only a layer below (the base) holds it writes a removal row — `-` in bases — that takes the name out of the
stack, and it says when records of the corpus still write the name (a warning, never a refusal). `check` is the linter over
the writable layer, one layer (`--layer`) or every layer (`--all`) and the sum; exit 1 when a finding is hard. `explain`
says, for one name, what each naming function answers and which layer's entry gave it, or that the rule did.

`pin` writes one row of `patronymics.tsv` into the writable layer: a short patronymic read back to its father and its modern
form (`--father`, `--modern`) — one more historical spelling, which `validate_old_patronymic` and `canonicalize_patronymic`
then know, while what the father's forms give (`derive_old_patronymic`) stays as it was, so no record's output moves —, or
(`--old`) a modern form's short one; none of the three, a form known and tied to nothing. The row is read by the same linter:
LEX001 (a key no lookup asks by, a pin of a father with no sex), LEX003 (a father no layer holds as a man's name) and LEX007
refuse it. A pin over a form the sum reads already is written and said: the records writing that form read it otherwise.
`--replace` replaces the layer's pin of the key. `unpin` deletes the layer's pin of a key; a pin of a layer below is not the
layer's to remove.

`add --replace` replaces the row of a key the layer holds already, whole, instead of refusing it: each table the command
writes (`names.tsv`, and `forms.tsv` when forms are given) has that key's row replaced, and a table it does not write is
left as it is — `--replace --base X` with no forms keeps the old `forms.tsv` row. The new row is read against the layers
below, not against the row it replaces, and a replaced row is printed as «replaced». A workspace of schema ≤ 5 refuses it.

A workspace of schema ≤ 5 keeps the old `names.csv`: `add` writes its row there as it always did (below), `explain` reads
the old tables compiled as one layer, `remove` and `check` are for layers.

Two rules govern where the row goes, and they are not the same rule.

**Alphabetical position is a preference.** The file is only roughly sorted —
572 of its rows sit out of order — so "everything above is smaller" is false and
a scan for the first larger row would land far too early. Placement follows the
NEAREST smaller name instead: the row goes after the last occurrence of the
largest `Имя` that is still `<=` the new one.

**Not shadowing is a hard constraint.** The table compiles into its layer
(`verso.ru.naming.legacy`) index by index «first row wins», so the FIRST row
carrying a key wins and later rows are the variants it deliberately shadows.
Inserting above a row that shares `Имя`, an old patronymic or a genitive would
silently steal that key from it. So placement may be pushed FORWARD past such a
row, never backward — an added row can be shadowed, but must never shadow.

The same «first row wins» is why this command will not sort the file and why
`verso.ru.linters.names_csv` does not check its order.

    python3 -m verso.ru.cli.names layer-diff --from-legacy DIR --base ru --oracle FILE --out DIR

writes the smallest layer (three TSV files, `verso.ru.naming.layer_files`) that makes the base answer every
question of an oracle file (`verso.ru.naming.oracle`, its format) as the old tables of DIR do
(`verso.ru.naming.layer_diff`, how its entries are chosen). The same inputs write the same bytes.
"""

import argparse
import sys
import time
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from verso.core import workspace
from verso.ru.gender import Gender
from verso.ru.linters.checks.lexicon import lint_layer
from verso.ru.linters.issue import line_text
from verso.ru.linters import names_layer as edit
from verso.ru.linters.names_csv import hard_findings, names_csv_path, read_rows
from verso.ru.messages import t
from verso.ru.naming import layer_diff, layers, names_registry, oracle, usage
from verso.ru.naming.layer_files import FilesLayer, LayerFileError
from verso.ru.naming.layers import BASES, LEGACY_FILES
from verso.ru.naming.legacy import compile_legacy
from verso.ru.naming.lexicon import FormsEntry, Layer, Lexicon, LexiconConflict, NameEntry
from verso.ru.naming.names_table import COLUMNS, _v, build_row, place, splice

#: The sex a `--gender` names: the letters of names.csv's «Пол», and `-` for the entry of a name with no sex.
GENDERS: dict[str, Gender | None] = {'М': Gender.MALE, 'Ж': Gender.FEMALE, '-': None}  # i18n: content — names.csv's «Пол»
def _form_options() -> tuple[tuple[str, tuple[str, ...], str], ...]:
    """The forms `add` takes: (the dest, the flags, the help), in the layer's columns' order."""
    return (('genitive', ('--genitive',), str(t("cli.names.help_genitive"))),
            ('patronymic_m', ('--patr-m', '--patronymic-m'), str(t("cli.names.help_patronymic_m"))),
            ('patronymic_f', ('--patr-f', '--patronymic-f'), str(t("cli.names.help_patronymic_f"))),
            ('old_patronymic_m', ('--patr-old-m', '--old-patronymic-m'), str(t("cli.names.help_old_patronymic_m"))),
            ('old_patronymic_f', ('--patr-old-f', '--old-patronymic-f'), str(t("cli.names.help_old_patronymic_f"))))


#: The dests of those options, as the layer's forms columns are named.
FORM_DESTS = edit.COLUMNS


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='verso names')
    sub = parser.add_subparsers(dest='command', required=True)

    diff = sub.add_parser('layer-diff', help=str(t("cli.names.layer_diff_help")),
                          description=str(t("cli.names.layer_diff_description")),
                          formatter_class=argparse.RawDescriptionHelpFormatter)
    diff.add_argument('--from-legacy', required=True, metavar='DIR', help=str(t("cli.names.help_from_legacy")))
    diff.add_argument('--base', required=True, choices=sorted(BASES), help=str(t("cli.names.help_base")))
    diff.add_argument('--oracle', required=True, metavar='FILE', help=str(t("cli.names.help_oracle")))
    diff.add_argument('--out', required=True, metavar='DIR', help=str(t("cli.names.help_out")))

    add = sub.add_parser('add', help=str(t("cli.names.add_help")), description=str(t("cli.names.add_description")),
                         formatter_class=argparse.RawDescriptionHelpFormatter)
    add.add_argument('--gender', required=True, choices=['М', 'Ж'])  # i18n: content — names.csv's «Пол»
    add.add_argument('--name', required=True, help=str(t("cli.names.help_name")))
    add.add_argument('--base', default='', help=str(t("cli.names.help_add_base")))
    add.add_argument('--origin', default='', help=str(t("cli.names.help_origin")))
    add.add_argument('--declension', default='', help=str(t("cli.names.help_declension")))
    for dest, flags, text in _form_options():
        add.add_argument(*flags, dest=dest, default=None, help=text)
    add.add_argument('--source', default='', help=str(t("cli.names.help_source")))
    add.add_argument('--layer', default=None, metavar='DIR', help=str(t("cli.names.help_layer")))
    add.add_argument('--replace', action='store_true', help=str(t("cli.names.help_replace")))
    add.add_argument('--path', default=None, help=str(t("cli.names.help_path")))
    add.add_argument('--dry-run', action='store_true')

    remove = sub.add_parser('remove', help=str(t("cli.names.remove_help")),
                            description=str(t("cli.names.remove_description")))
    remove.add_argument('--gender', required=True, choices=list(GENDERS), help=str(t("cli.names.help_remove_gender")))
    remove.add_argument('--name', required=True, help=str(t("cli.names.help_name")))
    remove.add_argument('--layer', default=None, metavar='DIR', help=str(t("cli.names.help_layer")))
    remove.add_argument('--dry-run', action='store_true')

    pin = sub.add_parser('pin', help=str(t("cli.names.pin_help")), description=str(t("cli.names.pin_description")),
                         formatter_class=argparse.RawDescriptionHelpFormatter)
    pin.add_argument('--gender', required=True, choices=list(GENDERS), help=str(t("cli.names.help_pin_gender")))
    pin.add_argument('--form', required=True, help=str(t("cli.names.help_pin_form")))
    pin.add_argument('--father', default='', help=str(t("cli.names.help_pin_father")))
    pin.add_argument('--modern', default='', help=str(t("cli.names.help_pin_modern")))
    pin.add_argument('--old', default='', help=str(t("cli.names.help_pin_old")))
    pin.add_argument('--source', default='', help=str(t("cli.names.help_source")))
    pin.add_argument('--layer', default=None, metavar='DIR', help=str(t("cli.names.help_layer")))
    pin.add_argument('--replace', action='store_true', help=str(t("cli.names.help_pin_replace")))
    pin.add_argument('--dry-run', action='store_true')

    unpin = sub.add_parser('unpin', help=str(t("cli.names.unpin_help")), description=str(t("cli.names.unpin_description")))
    unpin.add_argument('--gender', required=True, choices=list(GENDERS), help=str(t("cli.names.help_pin_gender")))
    unpin.add_argument('--form', required=True, help=str(t("cli.names.help_pin_form")))
    unpin.add_argument('--layer', default=None, metavar='DIR', help=str(t("cli.names.help_layer")))
    unpin.add_argument('--dry-run', action='store_true')

    check = sub.add_parser('check', help=str(t("cli.names.check_help")),
                           description=str(t("cli.names.check_description")))
    scope = check.add_mutually_exclusive_group()
    scope.add_argument('--layer', default=None, metavar='DIR', help=str(t("cli.names.help_check_layer")))
    scope.add_argument('--all', action='store_true', help=str(t("cli.names.help_check_all")))

    explain = sub.add_parser('explain', help=str(t("cli.names.explain_help")),
                             description=str(t("cli.names.explain_description")))
    explain.add_argument('name')
    explain.add_argument('--gender', choices=list(GENDERS), default=None, help=str(t("cli.names.help_explain_gender")))

    args = parser.parse_args(argv)
    if args.command == 'layer-diff':
        return _layer_diff(Path(args.from_legacy), args.base, Path(args.oracle), Path(args.out))
    ws = workspace.current()
    try:
        if args.command == 'explain':
            return _explain(ws, args.name, GENDERS[args.gender] if args.gender else None, args.gender is not None)
        if ws.names_layers is None:  # schema ≤ 5: the old names.csv
            if args.command != 'add':
                print(t("cli.names.no_layers", config=ws.root / workspace.CONFIG, command=args.command), file=sys.stderr)
                return 1
            return _add_legacy(args, ws)
        if args.command == 'add':
            return _add(ws, args)
        if args.command == 'remove':
            return _remove(ws, args)
        if args.command == 'pin':
            return _pin(ws, args)
        if args.command == 'unpin':
            return _unpin(ws, args)
        return _check(ws, Path(args.layer) if args.layer else None, args.all)
    except (edit.EditError, LayerFileError, LexiconConflict) as error:  # said, with the file or the key, never a traceback
        print(f'error: {error}', file=sys.stderr)
        return 1


def _add_legacy(args: argparse.Namespace, ws: workspace.Workspace) -> int:
    """`add` into the old names.csv (a workspace of schema ≤ 5; `--path` another file)."""
    if args.layer is not None:
        print(t("cli.names.layer_needs_schema_6", config=ws.root / workspace.CONFIG), file=sys.stderr)
        return 1
    if args.replace:
        print(t("cli.names.replace_needs_schema_6", config=ws.root / workspace.CONFIG), file=sys.stderr)
        return 1
    args.path = args.path or str(names_csv_path())
    print(t("cli.names.legacy_note", config=ws.root / workspace.CONFIG), file=sys.stderr)

    rows = read_rows(args.path)
    new_row = build_row(
        gender=args.gender, name=args.name, base=args.base, origin=args.origin,
        declension=args.declension, genitive=args.genitive or '',
        patr_old_m=args.old_patronymic_m or '', patr_old_f=args.old_patronymic_f or '',
        patr_m=args.patronymic_m or '', patr_f=args.patronymic_f or '', source=args.source)

    try:
        at = place(rows, new_row)
    except ValueError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1

    line = at + 2  # header is line 1
    neighbour = _v(rows[at - 1], 'Имя') if at else str(t("cli.names.top_of_file"))  # i18n: content — names.csv's column
    print(t("cli.names.placed", path=args.path, line=line, neighbour=neighbour))
    print('  ' + ','.join(new_row[c] for c in COLUMNS))

    if args.dry_run:
        print(t("cli.names.dry_run"))
        return 0

    updated = [*rows[:at], new_row, *rows[at:]]
    findings = hard_findings(updated)
    if findings:
        for f in findings:
            print(f'error: {f.code} line {f.line}: {f.name}: {f.message}', file=sys.stderr)
        return 1

    splice(args.path, at, new_row)
    return 0


def _add(ws: workspace.Workspace, args: argparse.Namespace) -> int:
    """`add` into a layer: the new rows read by the layers' linter over the layers under them, written when none is hard."""
    if args.path is not None:
        print(t("cli.names.path_needs_schema_5", config=ws.root / workspace.CONFIG), file=sys.stderr)
        return 1
    for option in ('origin', 'declension'):
        if getattr(args, option):
            print(t("cli.names.legacy_only", option=f'--{option}'), file=sys.stderr)
            return 1
    at = edit.target(ws, Path(args.layer) if args.layer else None)
    forms = {dest: getattr(args, dest) for dest in FORM_DESTS if getattr(args, dest) is not None}
    sex = GENDERS[args.gender]
    assert sex is not None  # `add` takes М and Ж alone
    entries = edit.new_entries(at, sex, args.name, args.base or None, forms,
                               args.source or edit.DEFAULT_SOURCE, replace=args.replace)
    found = edit.findings_of(at, entries, replace=args.replace)
    over = edit.replaced(at, entries) if args.replace else []
    hard = [f for f in found if f.issue.level == 'error']
    for f in hard:
        print(f'error: {f.issue.message}', file=sys.stderr)
    if hard:
        print(t("cli.names.refused", layer=at.layer.name, count=len(hard)), file=sys.stderr)
        return 1
    for f in found:
        print(t("cli.names.warning", message=f.issue.message), file=sys.stderr)
    for entry in entries:
        file = "names.tsv" if isinstance(entry, NameEntry) else "forms.tsv"
        if entry in over:
            print(t("cli.names.replaced", layer=at.layer.name, file=file, sex=_sex(entry.sex), name=entry.name))
        else:
            print(t("cli.names.added", layer=at.layer.name, file=file, sex=_sex(entry.sex), name=entry.name))
    if not args.dry_run:
        at.layer.put_all(entries)  # both files or neither
    if args.dry_run:
        print(t("cli.names.dry_run"))
    else:
        names_registry.reload()
    return 0


def _sex(sex: Gender | None) -> str:
    return {Gender.MALE: 'М', Gender.FEMALE: 'Ж', None: '—'}[sex]  # i18n: content — names.csv's «Пол»


def _remove(ws: workspace.Workspace, args: argparse.Namespace) -> int:
    """`remove`: the layer's rows of the key deleted, or a removal row for a name only a lower layer holds."""
    at = edit.target(ws, Path(args.layer) if args.layer else None)
    sex = GENDERS[args.gender]
    done = edit.remove(at, sex, args.name, write=not args.dry_run)
    if done.removal_row:
        print(t("cli.names.removed_tombstone", layer=at.layer.name, name=args.name, sex=_sex(sex)))
    else:
        print(t("cli.names.removed_rows", layer=at.layer.name, name=args.name, sex=_sex(sex),
                tables=', '.join(f'{table}.tsv' for table in done.deleted)))
    if done.still_held:
        print(t("cli.names.still_held", name=args.name, sex=_sex(sex)))
    if done.dangling:
        print(t("cli.names.dangling", name=args.name, count=len(done.dangling), names=', '.join(done.dangling)),
              file=sys.stderr)
    used = usage.written_count(ws, args.name)
    if used:
        print(t("cli.names.used", name=args.name, count=used), file=sys.stderr)
    if args.dry_run:
        print(t("cli.names.dry_run"))
    else:
        names_registry.reload()
    return 0


def _pin(ws: workspace.Workspace, args: argparse.Namespace) -> int:
    """`pin`: one row of patronymics.tsv, read by the layers' linter over the layers under it, written when no finding is
    hard; a pin that changes what the sum reads a form as is said."""
    at = edit.target(ws, Path(args.layer) if args.layer else None)
    sex = GENDERS[args.gender]
    entry = edit.new_pin(at, sex, args.form, args.father, args.modern, args.old, args.source or edit.DEFAULT_SOURCE,
                         replace=args.replace)
    found = edit.findings_of(at, [entry], replace=args.replace)
    hard = [f for f in found if f.issue.level == 'error']
    for f in hard:
        print(f'error: {f.issue.message}', file=sys.stderr)
    if hard:
        print(t("cli.names.refused", layer=at.layer.name, count=len(hard)), file=sys.stderr)
        return 1
    for f in found:
        print(t("cli.names.warning", message=f.issue.message), file=sys.stderr)
    change = edit.reading_change(at, entry)
    if change is not None:
        before, after = change
        print(t("cli.names.warning", message=t("cli.names.pin_rereads", form=entry.form, before=_read(before),
                                                after=_read(after))), file=sys.stderr)
    reading = _read(edit.Reading(entry.father, entry.modern, entry.old))
    if entry.key in at.here.patronymics:
        print(t("cli.names.pin_replaced", layer=at.layer.name, sex=_sex(sex), form=entry.form, reading=reading))
    else:
        print(t("cli.names.pinned", layer=at.layer.name, sex=_sex(sex), form=entry.form, reading=reading))
    if args.dry_run:
        print(t("cli.names.dry_run"))
        return 0
    at.layer.put(entry)
    names_registry.reload()
    return 0


def _read(reading: edit.Reading) -> str:
    """A pin's reading as the commands say it: «father, modern», «→ short» for a modern form's, «—» for a form tied to
    nothing."""
    if reading.old is not None:
        return f'→ {reading.old}'
    return ', '.join(cell for cell in (reading.father, reading.modern) if cell) or '—'


def _unpin(ws: workspace.Workspace, args: argparse.Namespace) -> int:
    """`unpin`: the layer's pin of the key deleted."""
    at = edit.target(ws, Path(args.layer) if args.layer else None)
    sex = GENDERS[args.gender]
    done = edit.remove_pin(at, sex, args.form, write=not args.dry_run)
    print(t("cli.names.unpinned", layer=at.layer.name, sex=_sex(sex), form=args.form))
    if done.still_held:
        print(t("cli.names.pin_still_held", form=args.form, sex=_sex(sex)))
    if args.dry_run:
        print(t("cli.names.dry_run"))
    else:
        names_registry.reload()
    return 0


def _check(ws: workspace.Workspace, directory: Path | None, everything: bool) -> int:
    """`check`: the layers' linter over the writable layer (else every layer above the base), one layer, or every layer
    and the sum; 1 when a finding is hard."""
    config = ws.names_layers
    assert config is not None
    stack = layers.sources(ws)
    has_base = config.base is not None
    if directory is not None:
        chosen = [edit.layer_index(ws, directory)]
    elif everything:
        chosen = list(range(len(stack)))
    elif config.writable is not None:
        chosen = [edit.layer_index(ws, config.writable)]
    else:
        chosen = list(range(1 if has_base else 0, len(stack)))
    loaded = [source.load() for source in stack]
    hard = advice = 0
    for n in chosen:
        source = stack[n]
        if not isinstance(source, FilesLayer):
            print(t("cli.names.check_old_table", layer=source.name))
            continue
        for found in lint_layer(source, below=loaded[:n], base=has_base and n == 0):
            print(line_text(f"{source.name}/{found.file}", found.issue))
            if found.issue.level == 'error':
                hard += 1
            else:
                advice += 1
    if everything:
        try:
            Lexicon.of(loaded).complete()
        except LexiconConflict as conflict:
            print(t("cli.names.check_sum", error=str(conflict)))
            hard += 1
    print(t("cli.names.check_summary", layers=', '.join(stack[n].name for n in chosen), hard=hard, advice=advice))
    return 1 if hard else 0


#: What `explain` asks about a name: (function, the arguments after the name, which are the name's sex, a child's sex or none).
_ASKED = (('canonicalize_name', 'sex'), ('matching_base', 'sex'), ('genitive_given_name', 'sex'),
          ('get_gender_from_name', None), ('derive_patronymic', 'child'), ('derive_old_patronymic', 'child'))
#: The forms column each function's answer is read from, by the child's sex where it has one.
_COLUMN: dict[str, dict[Gender | None, str]] = {'genitive_given_name': {None: 'genitive'},
           'derive_patronymic': {Gender.MALE: 'patronymic_m', Gender.FEMALE: 'patronymic_f'},
           'derive_old_patronymic': {Gender.MALE: 'old_patronymic_m', Gender.FEMALE: 'old_patronymic_f'}}


def _explain(ws: workspace.Workspace, name: str, sex: Gender | None, sexed: bool) -> int:
    """`explain`: each function's answer for `name`, and the entry of which layer gave it."""
    names_registry.reload()
    loaded = [source.load() for source in layers.sources(ws)]
    lexicon = Lexicon.of(loaded)
    facts = lexicon.by_name.get(name)
    held = [g for g, entry in ((Gender.MALE, facts and facts.male), (Gender.FEMALE, facts and facts.female)) if entry]
    sexes: list[Gender | None] = [sex] if sexed else [*held] if held else [None]
    questions: list[oracle.Row] = []
    for function, kind in _ASKED:
        for other in ([None] if kind is None else [Gender.MALE, Gender.FEMALE] if kind == 'child' else sexes):
            args = [name] if kind is None else [name, oracle.encode(other)]
            questions.append(oracle.Row(function, tuple(args), None))
    answered = oracle.answers(questions, lexicon)
    for row, got in zip(questions, answered, strict=True):
        shown = ', '.join(str(a) if a is not None else '—' for a in row.args)
        print(t("cli.names.explain_call", call=f'{row.function}({shown})', answer=oracle.dumps(got.answer)))
        by_sex = _COLUMN.get(row.function, {})
        column = by_sex.get(None) or by_sex.get(_GENDER_OF.get(row.args[1]) if len(row.args) > 1 else None)
        for kind, key in sorted(got.keys):
            if kind in ('ignore_name', 'ignore_patronymic'):
                continue
            for line in _provenance(lexicon, loaded, kind, key, column):
                print(line)
    return 0


_GENDER_OF = {'M': Gender.MALE, 'F': Gender.FEMALE}


def _provenance(lexicon: Lexicon, loaded: list[Layer], kind: str, key: str, column: str | None) -> list[str]:
    """The lines saying which entries answered a lookup (`Lexicon.explain`). A name's lookup also gives its forms —
    those a layer writes, and the rule's where no layer writes them for a name a deriving layer holds."""
    entries = lexicon.explain(kind, key)
    if not entries:
        return [str(t("cli.names.explain_unknown", kind=kind, key=key))]
    by_layer = {layer.name: layer for layer in loaded}
    out: list[str] = []
    forms_of: set[Gender] = set()
    for layer, entry in entries:
        if isinstance(entry, NameEntry):
            bases = f" → {'|'.join(entry.bases)}" if entry.bases else ''
            out.append(str(t("cli.names.explain_name", layer=layer, sex=_sex(entry.sex), name=entry.name, bases=bases,
                             source=entry.source)))
            if kind == 'name' and entry.sex is not None:
                forms_of.add(entry.sex)
        elif isinstance(entry, FormsEntry):
            forms_of.add(entry.sex)
        else:
            out.append(str(t("cli.names.explain_pin", layer=layer, sex=_sex(entry.sex), form=entry.form,
                             father=entry.father or '—', modern=entry.modern or '—', old=entry.old or '—')))
    if kind != 'name':  # a form's lookup names the forms entries it was read from
        forms_of = {entry.sex for _, entry in entries if isinstance(entry, FormsEntry)}
        names_of = {entry.name for _, entry in entries if isinstance(entry, FormsEntry)}
    else:
        names_of = {key}
    if column is not None:  # only a function that reads a form shows it, and only the cell it reads
        for name in sorted(names_of):
            for sex in sorted(forms_of, key=lambda g: g is Gender.FEMALE):
                line = _forms_line(lexicon, by_layer, sex, name, column)
                if line:
                    out.append(line)
    return out


def _forms_line(lexicon: Lexicon, by_layer: dict[str, Layer], sex: Gender, name: str, column: str) -> str | None:
    """The cell `column` of the forms of (`sex`, `name`) the lexicon answers by, with where it is from: the layer that
    writes it, or «rule» (`verso.ru.naming.forms`) — None where no layer holds the forms and none derives them."""
    filled = lexicon.forms_of(sex, name)
    if filled is None:
        return None
    own = next((entry for entry in (by_layer[n].forms.get((sex, name)) for n in reversed(lexicon.layers))
                if entry is not None), None)
    layer = next((n for n in reversed(lexicon.layers) if by_layer[n].forms.get((sex, name)) is not None), None)
    where = layer if own is not None and getattr(own, column) is not None else str(t("cli.names.explain_rule"))
    return str(t("cli.names.explain_forms", layer=layer or str(t("cli.names.explain_rule")), sex=_sex(sex), name=name,
                 cell=column, value=getattr(filled, column) or '—', where=where))


def _layer_diff(legacy_dir: Path, base: str, oracle_file: Path, out: Path) -> int:
    """`verso names layer-diff`: the layer written, what it holds said; 1 when questions are left unsettled (the layer
    written all the same, for reading)."""
    started = time.monotonic()
    legacy = compile_legacy(*(legacy_dir / name for name in LEGACY_FILES))
    rows = oracle.parse(oracle_file)
    try:
        result = layer_diff.minimal_layer(legacy, [BASES[base]().load()], rows)
        left: layer_diff.LayerDiffError | None = None
    except layer_diff.LayerDiffError as error:
        result, left = error.result, error
    except (layer_diff.LayerDiffConflict, oracle.OracleError) as error:
        print(error, file=sys.stderr)
        return 1
    layer_diff.write(result, out)
    counts, reasons = result.counts(), Counter(result.reasons[key] for key in result.entries)
    print(t("cli.names.layer_diff_done", out=out, names=counts["names"], forms=counts["forms"],
            patronymics=counts["patronymics"], questions=len(rows), derived=result.derived,
            differing=result.differing,
            direct=reasons["question"], along=sum(reasons.values()) - reasons["question"], rounds=result.rounds,
            seconds=f"{time.monotonic() - started:.1f}"))
    if result.stale:
        print(t("cli.names.layer_diff_stale", count=result.stale, oracle=oracle_file, legacy=legacy_dir),
              file=sys.stderr)
    if left is not None:
        print(left, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
