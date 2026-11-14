"""The святцы: import the table, and ask it while reading a scan.

    python3 -m verso.ru.cli.svyatcy near 1850-04-16 --gender F --like Мария
    python3 -m verso.ru.cli.svyatcy dates Агапия --gender F
    python3 -m verso.ru.cli.svyatcy coverage --village Горюхино
    python3 -m verso.ru.cli.svyatcy import --source <cu-md-sandbox>/Trebnik1906/chapters/27alf_names.md \
        --commit <sha>

`near` is the reading aid: which names of that gender the Church kept around
a day, ranked by how closely each resembles what you think the scan says.
When «Агапія» and «Марія» both fit the ink of a child christened on
16 April, the святцы answer at once — Агапия is kept on the 16th only.

`import` rebuilds `verso/ru/church_calendar/data/svyatcy_1906.tsv` from the
upstream Markdown. It is deterministic and holds only what the book prints;
how a name reaches it (names.csv, `ALSO_KEPT`) is code, not data.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Sequence
from difflib import SequenceMatcher
from pathlib import Path

from verso.ru.church_calendar.church_slavonic import modern_name, parse_alphabet
from verso.ru.church_calendar.julian import is_valid
from verso.ru.church_calendar.svyatcy import (
    COLUMNS, DATA, Near, format_dates, load_svyatcy)
from verso.ru.gender import Gender
from verso.ru.messages import t

UPSTREAM = "https://github.com/slavonic/cu-md-sandbox"
UPSTREAM_FILE = "Trebnik1906/chapters/27alf_names.md"

_GENDERS = {"M": Gender.MALE, "F": Gender.FEMALE, "М": Gender.MALE, "Ж": Gender.FEMALE}  # i18n: content — the genders the option takes


def _date(text: str) -> tuple[int, int, int]:
    y, m, d = (int(p) for p in text.split("-"))
    if not is_valid(y, m, d):
        raise argparse.ArgumentTypeError(t("cli.svyatcy.no_such_day", text=text))
    return y, m, d


def build_table(markdown: str, commit: str) -> tuple[str, list[str]]:
    """The TSV text for the alphabet, and every token the parser could not
    place (the import fails on any)."""
    entries, unread = parse_alphabet(markdown)
    lines = [
        "# «Алфавит имён всех святых» — Требник, Синодальная типография, Москва, 1906.",  # i18n: content — the table's header, written into the committed file
        f"# Source: {UPSTREAM}/blob/{commit}/{UPSTREAM_FILE} (MIT, see LICENSE.svyatcy).",
        "# Regenerate: verso svyatcy import --source … --commit …",
        "\t".join(COLUMNS),
    ]
    for e in entries:
        dates = format_dates(e.dates)
        lines.append("\t".join((e.gender, e.headword, modern_name(e.headword), dates, "")))
        for alt in e.alternates:
            lines.append("\t".join((e.gender, alt, modern_name(alt), dates, e.headword)))
    problems = [f"{u.headword}: {u.token}" for u in unread]
    for e in entries:
        for m, d in e.dates:
            if not is_valid(1800, m, d):  # a leap year, so 29 February passes
                problems.append(str(t("cli.svyatcy.no_day", headword=e.headword, d=d, m=m)))
    return "\n".join(lines) + "\n", problems


def _import(args: argparse.Namespace) -> int:
    table, problems = build_table(Path(args.source).read_text(encoding="utf-8"), args.commit)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    if args.out:
        out = Path(args.out)
    elif isinstance(DATA, Path):
        out = DATA
    else:
        print(t("cli.svyatcy.table_not_on_disk"), file=sys.stderr)
        return 2
    out.write_text(table, encoding="utf-8")
    rows = table.count("\n") - 4
    print(t("cli.svyatcy.written", out=out, count=rows))
    return 0


def rank(near: list[Near], like: str | None) -> list[Near]:
    """Nearest first; with `like`, most similar to it first — compared with
    both the book's form and ours, so «Иван» finds «Иоанн»."""
    if not like:
        return near
    low = like.lower()

    def similarity(n: Near) -> float:
        return max(SequenceMatcher(None, low, n.name.lower()).ratio(),
                   SequenceMatcher(None, low, n.base.lower()).ratio())

    return sorted(near, key=lambda n: (-round(similarity(n), 2), abs(n.offset), n.name))


def _near(args: argparse.Namespace) -> int:
    svyatcy = load_svyatcy()
    found = rank(svyatcy.names_near(args.date, _GENDERS[args.gender],
                                    args.window, args.window), args.like)
    y, m, d = args.date
    print(t("cli.svyatcy.near", gender=_GENDERS[args.gender].value, d=d, m=m, y=y,
            window=t("cli.facts.span.days", count=args.window), count=len(found)))
    for n in found[:args.limit]:
        shown = n.name if n.base == n.name else f"{n.name} ({n.base})"
        print(f"  {n.offset:+3d}  {n.day[1]:02d}.{n.day[0]:02d}  {shown}")
    return 0


def _dates(args: argparse.Namespace) -> int:
    svyatcy = load_svyatcy()
    days = svyatcy.commemorations(args.name, _GENDERS[args.gender])
    if not days:
        print(t("cli.svyatcy.not_kept", name=args.name))
        return 1
    print(f"{args.name}: " + ", ".join(f"{d:02d}.{m:02d}" for m, d in days))
    return 0


def _coverage(args: argparse.Namespace) -> int:
    from verso.ru.cli.facts import load
    from verso.ru.facts.model import NameClaim

    svyatcy = load_svyatcy()
    facts = load(Path(args.village), "birth").believed()
    names: Counter[tuple[str, Gender]] = Counter()
    for claim in facts.of(NameClaim):
        if claim.cite.locator == "child" and claim.given and claim.gender is not None:
            names[(claim.given, claim.gender)] += 1
    total = sum(names.values())
    missing = Counter({k: n for k, n in names.items() if not svyatcy.knows(*k)})
    known = total - sum(missing.values())
    share = known / total if total else 0.0
    print(t("cli.svyatcy.coverage", village=args.village, known=known,
            of_births=t("counted.of_births", count=total), share=share))
    for (name, gender), n in missing.most_common(args.limit):
        print(f"  {n:4d}  {name} ({gender.value})")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verso svyatcy")
    sub = parser.add_subparsers(dest="command", required=True)

    near = sub.add_parser("near", help=str(t("cli.svyatcy.help_near")))
    near.add_argument("date", type=_date, help=str(t("cli.svyatcy.help_date")))
    near.add_argument("--gender", required=True, choices=sorted(_GENDERS))
    near.add_argument("--like", help=str(t("cli.svyatcy.help_like")))
    near.add_argument("--window", type=int, default=7)
    near.add_argument("--limit", type=int, default=25)

    dates = sub.add_parser("dates", help=str(t("cli.svyatcy.help_days")))
    dates.add_argument("name")
    dates.add_argument("--gender", required=True, choices=sorted(_GENDERS))

    coverage = sub.add_parser("coverage", help=str(t("cli.svyatcy.help_coverage")))
    coverage.add_argument("--village", required=True)
    coverage.add_argument("--limit", type=int, default=30)

    imp = sub.add_parser("import", help=str(t("cli.svyatcy.help_import")))
    imp.add_argument("--source", required=True, help=str(t("cli.svyatcy.help_upstream", file=UPSTREAM_FILE)))
    imp.add_argument("--commit", required=True, help=str(t("cli.svyatcy.help_sha")))
    imp.add_argument("--out", help="where to write the table (default: the package's own, when it is on disk)")

    args = parser.parse_args(argv)
    handlers = {"near": _near, "dates": _dates, "coverage": _coverage, "import": _import}
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
