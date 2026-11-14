"""Show, add, remove and check the transliteration's rules; move the corpus's old `transliteration.toml` into a layer.

    verso translit show Сорокоплехин [Плотвичкин …]
    verso translit add Сорокоплехин Sorokoplekhine [--profile ru-v2] [--dry-run]
    verso translit remove Сорокоплехин [--profile ru-v2] [--dry-run]
    verso translit check [--layer DIR]
    verso translit migrate

A workspace of schema 7 says which profile each role spells by (`[translit] address`, `display`) and keeps its rules as
rows of the names layers (`translit.tsv`, `verso.ru.naming.translit_layers`). `show` prints, for each word, what each role
gives — the profile, the rule of that profile if a layer holds one, the result. `add` writes a rule of the profile of
display (`--profile` another) into the writable layer, after the layers' linter has read it (LEX008 a rule that cannot be
used and LEX010 a Latin spelling with other characters refuse it); a rule of the profile that spells the addresses is
refused while a generated tree holds a res_name it would rename. `remove` takes a rule away (a `-` row for one only a
layer below holds). `check` lints every layer's rules (`--layer` one); `migrate` writes the corpus's `transliteration.toml`
into the writable layer as rules of `ru-v1` and leaves the file for its owner to remove. Exit 1 on a refusal or a hard
finding.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from verso.core import workspace
from verso.ru.linters import translit_layer as edit
from verso.ru.linters.checks.translit import lint_rules
from verso.ru.linters.issue import line_text
from verso.ru.messages import t
from verso.ru.naming import translit_layers


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verso translit", description=str(t("cli.translit.description")))
    sub = parser.add_subparsers(dest="command", required=True)
    show = sub.add_parser("show", help=str(t("cli.translit.show_help")))
    show.add_argument("words", nargs="+", help=str(t("cli.translit.help_word")))
    add = sub.add_parser("add", help=str(t("cli.translit.add_help")))
    add.add_argument("word", help=str(t("cli.translit.help_word")))
    add.add_argument("latin", help=str(t("cli.translit.help_latin")))
    remove = sub.add_parser("remove", help=str(t("cli.translit.remove_help")))
    remove.add_argument("word", help=str(t("cli.translit.help_word")))
    for p in (add, remove):
        p.add_argument("--profile", help=str(t("cli.translit.help_profile")))
        p.add_argument("--dry-run", action="store_true", help=str(t("cli.translit.help_dry_run")))
    check = sub.add_parser("check", help=str(t("cli.translit.check_help")))
    check.add_argument("--layer", type=Path, help=str(t("cli.translit.help_layer")))
    sub.add_parser("migrate", help=str(t("cli.translit.migrate_help")))
    args = parser.parse_args(argv)

    ws = workspace.current()
    try:
        if args.command == "show":
            return _show(ws, args.words)
        if args.command == "add":
            done = edit.add_rule(ws, args.word, args.latin, profile=args.profile, dry_run=args.dry_run)
            print(t("cli.translit.added", word=done.word, latin=done.latin, profile=done.profile, layer=done.layer))
            if done.redundant:
                print(t("cli.translit.redundant", word=done.word, latin=done.latin, profile=done.profile),
                      file=sys.stderr)
        elif args.command == "remove":
            done = edit.remove_rule(ws, args.word, profile=args.profile, dry_run=args.dry_run)
            print(t("cli.translit.removed", word=done.word, latin=done.latin, profile=done.profile,
                    gives=done.profile_gives, layer=done.layer))
        elif args.command == "check":
            return _check(ws, args.layer)
        else:
            path, written = edit.migrate(ws)
            print(t("cli.translit.migrated", count=written, layer=translit_layers.writable(ws).name, path=path))
            return 0
    except edit.RuleRefused as refused:
        print(str(refused), file=sys.stderr)
        return 1
    if args.command in ("add", "remove") and args.dry_run:
        print(t("cli.translit.dry_run"))
    return 0


def _show(ws: workspace.Workspace, words: Sequence[str]) -> int:
    for word in words:
        for found in edit.explain(ws, word):
            if found.rule is None:
                print(t("cli.translit.show_profile", word=word, role=found.role, profile=found.profile,
                        result=found.result))
            else:
                print(t("cli.translit.show_rule", word=word, role=found.role, profile=found.profile,
                        gives=found.profile_gives, result=found.result, layer=found.rule.layer))
    return 0


def _check(ws: workspace.Workspace, layer: Path | None) -> int:
    hard = advice = 0
    below: dict[translit_layers.Key, translit_layers.TranslitRule] = {}
    names: list[str] = []
    for source in translit_layers.sources(ws):
        chosen = layer is None or (isinstance(source, translit_layers.FileRules)
                                   and Path(str(source.directory)).resolve() == layer.resolve())
        if chosen and isinstance(source, translit_layers.FileRules):
            names.append(source.name)
            for found in lint_rules(translit_layers.read_rows(source.path), below=below):
                print(line_text(f"{source.name}/{found.file}", found.issue))
                if found.issue.level == "error":
                    hard += 1
                else:
                    advice += 1
        for key, rule in source.load().items():
            if rule.latin is None:
                below.pop(key, None)
            else:
                below[key] = rule
    print(t("cli.translit.check_summary", layers=", ".join(names), hard=hard, advice=advice))
    return 1 if hard else 0


if __name__ == "__main__":
    raise SystemExit(main())
