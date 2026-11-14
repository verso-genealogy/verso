"""The workspace's corpus statuses as `statuses.toml`.

    verso statuses-toml                  # print the TOML of <[corpus] dir>/statuses.py
    verso statuses-toml --out FILE       # write it to FILE

A corpus may hold its landlords' statuses as data — `statuses.toml`, read without executing any
Python — instead of the module the DSL imports. A workspace holding both is refused, so the
migration is `--out <corpus dir>/statuses.toml` and then removing `statuses.py` by hand; there is
no flag that leaves both side by side.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from verso.core import corpus_data
from verso.ru.domain import statuses
from verso.ru.messages import t


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=str(t("cli.statuses_toml.description")))
    ap.add_argument("--out", help=str(t("cli.statuses_toml.help_out")))
    args = ap.parse_args(argv)
    path = corpus_data.corpus_file(statuses.CORPUS_STATUSES)
    if path is None:
        print(t("cli.statuses_toml.no_module", name=statuses.CORPUS_STATUSES), file=sys.stderr)
        return 1
    module = statuses.corpus_statuses()
    assert module is not None
    text = statuses.statuses_toml(module)
    if args.out:
        out = Path(args.out)
        out.write_text(text, encoding="utf-8")
        print(t("cli.statuses_toml.written", path=out))
        if out.resolve().parent == path.resolve().parent and out.name == statuses.CORPUS_STATUSES_TOML:
            print(t("cli.statuses_toml.both_now", py=path), file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
