"""`verso upgrade-dsl` — a village's DSL files from v0 to v1.

    verso upgrade-dsl --village Заманиловка [--check] [FILE …]
    verso upgrade-dsl [--check] FILE …

Each file's imports go through the facade and its `__main__` goes (`verso.ru.dsl.upgrade`);
nothing else of it changes, and the codemod checks that no record's ratchet print moves. The
corpus's own statuses are imported from `corpus.statuses`. A file it refuses is named with the
reason, and then no file is written. `--check` writes nothing and fails when a file would change.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from verso.core.pipeline.load import dsl_files
from verso.ru.domain import statuses
from verso.ru.dsl.upgrade import CORPUS, UpgradeError, upgrade
from verso.ru.messages import t


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--village", help=str(t("cli.upgrade_dsl.help_village")))
    ap.add_argument("--check", action="store_true", help=str(t("cli.upgrade_dsl.help_check")))
    ap.add_argument("files", nargs="*", help=str(t("cli.upgrade_dsl.help_files")))
    args = ap.parse_args(argv)
    village: str | None = args.village
    if args.files:
        files = [Path(f) for f in args.files]
    elif village is not None:
        files = dsl_files(Path(village))
    else:
        ap.error(str(t("cli.upgrade_dsl.nothing_named")))
    # A corpus whose statuses are `statuses.toml` alone has no module the DSL could import them from: none of
    # their names is a catalog's, and a v0 file naming one is refused.
    named = statuses.corpus_module_name()
    corpus = tuple(getattr(statuses.corpus_statuses(), "__all__", ())) if named is not None else ()
    module = named or CORPUS
    changed: dict[Path, str] = {}
    refused = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        try:
            new = upgrade(text, corpus, module)
        except UpgradeError as exc:
            refused.append(f"{path}: {exc}")
            continue
        if new != text:
            changed[path] = new
    if refused:
        print(*refused, sep="\n", file=sys.stderr)
        return 2
    if not args.check:
        for path, new in changed.items():
            path.write_text(new, encoding="utf-8")
    counts = str(t("cli.upgrade_dsl.counts", files=len(files), changed=len(changed), same=len(files) - len(changed)))
    print(f"{args.village}: {counts}" if args.village else counts)
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    sys.exit(main())
