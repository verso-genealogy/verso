"""export-records: a village's record sets as records-v1 JSON.

    python -m verso.ru.cli.export_records --village Горюхино [--out records] [--strict]

Writes `<out>/<village>/<YYYY>/<file>.json` and `index.json` (`verso.core.pipeline.records`);
`--out` defaults to `records/` at the workspace root, which git ignores. A DSL file
that does not import is skipped with a warning, as `discover_records` skips it, and
`--strict` turns that into exit 1.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from verso.core.pipeline.records import ExportError, export_village
from verso.ru.messages import t


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=str(t("cli.export_records.description")))
    ap.add_argument("--village", required=True, help=str(t("cli.export_records.help_village")))
    ap.add_argument("--out", help=str(t("cli.export_records.help_out")))
    ap.add_argument("--strict", action="store_true", help=str(t("cli.export_records.help_strict")))
    args = ap.parse_args(argv)
    if args.out:
        out = Path(args.out)
    else:
        from verso.core.workspace import current
        out = current().root / "records"
    try:
        exported = export_village(Path(args.village), out)
    except ExportError as exc:
        print(exc, file=sys.stderr)
        return 2
    target = out / Path(args.village).name
    print(t("cli.export_records.done", files=t("counted.files", count=len(exported.files)),
            records=t("counted.records", count=exported.records), target=target))
    if exported.skipped:
        print(t("cli.export_records.skipped", count=len(exported.skipped), where=target / 'index.json'), file=sys.stderr)
        if args.strict:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
