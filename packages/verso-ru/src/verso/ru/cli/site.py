"""site: a village's records as a static site — its books record by record, an index of the names,
a search.

    python -m verso.ru.cli.site --village Горюхино --out _site [--records DIR] [--docs DIR]
        [--title T] [--summary S] [--repo-url U] [--site-url U] [--revision R]
        [--license NAME --license-url U] [--strict]

The records are built as `export-records` builds them (or read from an export, `--records`), and
drawn by the interface's schema. `--out` is new or empty. The prose is `<village>/docs/*.md`
(`--docs`), which needs the extra `verso-ru[site]`. Exit 0; 1 with `--strict` when a DSL file did
not import or the built site holds a dead link; 2 for a refusal.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from verso.core.pipeline.records import INDEX, ExportError, export_village
from verso.ru.messages import t
from verso.ru.site import BuildError, build
from verso.ru.site.model import DuplicatePath
from verso.ru.site.prose import ProseError


def _read(root: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """The file nodes of an export of one village, and what it skipped."""
    index = json.loads((root / INDEX).read_text(encoding="utf-8"))
    files = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(root.rglob("*.json"))
             if path.name != INDEX]
    return files, dict(index.get("skipped") or {})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=str(t("cli.site.description")))
    ap.add_argument("--village", required=True, help=str(t("cli.site.help_village")))
    ap.add_argument("--out", required=True, help=str(t("cli.site.help_out")))
    ap.add_argument("--records", help=str(t("cli.site.help_records")))
    ap.add_argument("--docs", help=str(t("cli.site.help_docs")))
    ap.add_argument("--title", help=str(t("cli.site.help_title")))
    ap.add_argument("--summary", help=str(t("cli.site.help_summary")))
    ap.add_argument("--repo-url", help=str(t("cli.site.help_repo_url")))
    ap.add_argument("--site-url", help=str(t("cli.site.help_site_url")))
    ap.add_argument("--revision", help=str(t("cli.site.help_revision")))
    ap.add_argument("--license", dest="license_name", help=str(t("cli.site.help_license")))
    ap.add_argument("--license-url", help=str(t("cli.site.help_license_url")))
    ap.add_argument("--strict", action="store_true", help=str(t("cli.site.help_strict")))
    args = ap.parse_args(argv)
    village = Path(args.village)
    docs = Path(args.docs) if args.docs else village / "docs"
    try:
        if args.records:
            files, skipped = _read(Path(args.records) / village.name)
        else:
            with tempfile.TemporaryDirectory() as scratch:
                export_village(village, scratch)
                files, skipped = _read(Path(scratch) / village.name)
        from verso.core.workspace import current
        built = build(files, out=Path(args.out), village=village.name, title=args.title, docs=docs,
                      workspace=current().root, repo_url=args.repo_url, site_url=args.site_url,
                      revision=args.revision, summary=args.summary, license_name=args.license_name,
                      license_url=args.license_url)
    except (ExportError, BuildError, DuplicatePath, ProseError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        return 2
    print(t("cli.site.done", pages=built.pages, megabytes=f"{built.bytes / 1e6:.1f}",
            records=t("counted.records", count=built.records), unreviewed=built.unreviewed, out=built.out))
    for problem in built.problems[:50]:
        print(problem, file=sys.stderr)
    if skipped:
        print(t("cli.site.skipped", count=len(skipped)), file=sys.stderr)
    return 1 if args.strict and (skipped or built.problems) else 0


if __name__ == "__main__":
    sys.exit(main())
