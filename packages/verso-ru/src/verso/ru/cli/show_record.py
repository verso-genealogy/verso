"""Show the original source record for a given village/year/type/record number."""
import argparse
import re
import sys
from pathlib import Path

TYPE_MAP = {
    "рождение": "births",  # i18n: content — the record types --type takes
    "брак": "marriages",  # i18n: content — the record types --type takes
    "смерть": "deaths",  # i18n: content — the record types --type takes
    "развод": "divorces",  # i18n: content — the record types --type takes
    "ревизия": "census",  # i18n: content — the record types --type takes
}

# Number of context lines to show before/after each match
CONTEXT = 10


def find_record_blocks(path: Path, record_num: int, record_type_en: str) -> list[tuple[int, list[str]]]:
    """Return list of (start_line, lines) for each matching block."""
    lines = path.read_text(encoding="utf-8").splitlines()

    if record_type_en == "census":
        return _find_census_household(lines, record_num)

    # Match e.g. birth(52, or marriage(3, or death(4,
    func_name = record_type_en.rstrip("s")  # births→birth, marriages→marriage, deaths→death
    pattern = re.compile(rf"\b{func_name}\({record_num}\s*,")

    results = []
    for i, line in enumerate(lines):
        if pattern.search(line):
            start = max(0, i - 2)
            end = min(len(lines), i + CONTEXT + 1)
            results.append((i + 1, lines[start:end]))
    return results


def _find_census_household(lines: list[str], household_idx: int) -> list[tuple[int, list[str]]]:
    """Find the Nth household() block (0-indexed) in a census file."""
    household_pattern = re.compile(r"\bhousehold\(")
    household_starts: list[int] = []
    for i, line in enumerate(lines):
        if household_pattern.search(line):
            household_starts.append(i)

    if household_idx >= len(household_starts):
        return []

    start = max(0, household_starts[household_idx] - 2)
    # End is the next household start or end of file
    if household_idx + 1 < len(household_starts):
        end = household_starts[household_idx + 1]
    else:
        end = len(lines)
    return [(household_starts[household_idx] + 1, lines[start:end])]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Show original source record from a village data file."
    )
    parser.add_argument("village_dir", type=Path, help="Village directory")
    parser.add_argument("year", type=int, help="Year (e.g. 1807)")
    parser.add_argument(
        "type",
        choices=list(TYPE_MAP.keys()),
        help="Record type: рождение, брак, смерть, or ревизия",  # i18n: content — the values the option takes
    )
    parser.add_argument("record_num", type=int, help="Record number")
    args = parser.parse_args()

    village_dir = args.village_dir.resolve()
    record_type_en = TYPE_MAP[args.type]

    # Find source file via glob (village-agnostic)
    candidates = list(village_dir.glob(f"{args.year}/*_{record_type_en}_{args.year}.py"))
    if not candidates:
        print(f"Error: no *_{record_type_en}_{args.year}.py found in {village_dir / str(args.year)}", file=sys.stderr)
        sys.exit(1)

    path = candidates[0]
    blocks = find_record_blocks(path, args.record_num, record_type_en)

    if not blocks:
        print(f"No record #{args.record_num} found in {path}", file=sys.stderr)
        sys.exit(1)

    rel_path = path.relative_to(village_dir.parent)
    for line_num, block_lines in blocks:
        print(f"# {rel_path}  (line {line_num})")
        print()
        for line in block_lines:
            print(line)
        print()


if __name__ == "__main__":
    main()
