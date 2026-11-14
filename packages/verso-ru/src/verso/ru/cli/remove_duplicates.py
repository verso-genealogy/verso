#!/usr/bin/env python3
"""
Remove duplicate records from names.csv using smart deduplication.

Strategy:
1. Group by (gender, name, all patronymic columns)
2. For each duplicate group, select the best record:
   - Prefer records from authoritative sources (Петровский)
   - Prefer records with more complete information
   - Merge complementary information when possible
"""

import argparse
import csv
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from verso.ru.exporters.base import csv_dict_writer
from verso.ru.linters.names_csv import names_csv_path


class DuplicateRemover:
    """Remove duplicates from names.csv with smart merging."""

    # Columns used to identify duplicates
    DUPLICATE_KEY_COLUMNS: ClassVar[list[str]] = [
        'Пол',  # i18n: content — names.csv's column
        'Имя',  # i18n: content — names.csv's column
        'Имя-основа',  # i18n: content — names.csv's column
        'Отчество старое М',  # i18n: content — names.csv's column
        'Отчество старое Ж',  # i18n: content — names.csv's column
        'Отчество М',  # i18n: content — names.csv's column
        'Отчество Ж',  # i18n: content — names.csv's column
    ]

    # Source priority for selecting best record (higher = better)
    SOURCE_PRIORITY: ClassVar[dict[str, int]] = {
        'Словарь русских личных имен Петровского': 10,  # i18n: content — names.csv's «Источник» values
        '(для варианта целевого современного отчества)': 5,  # i18n: content — names.csv's «Источник» values
        'Новое имя': 3,  # i18n: content — names.csv's «Источник» values
        '-': 1,
        '': 0,
    }

    def __init__(self, csv_path: str | Path | None = None):
        self.csv_path = Path(csv_path) if csv_path is not None else names_csv_path()
        self.rows: list[dict[str, str]] = []
        self.fieldnames: list[str] = []
        self.backup_path: str = ""

    def create_backup(self) -> str:
        """Create timestamped backup of the CSV file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{self.csv_path}.backup_dedup_{timestamp}"

        with open(self.csv_path, 'r', encoding='utf-8') as src:
            with open(backup_path, 'w', encoding='utf-8') as dst:
                dst.write(src.read())

        self.backup_path = backup_path
        return backup_path

    def load_csv(self) -> None:
        """Load CSV file into memory."""
        with open(self.csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            self.fieldnames = list(reader.fieldnames or [])
            self.rows = list(reader)

    def group_duplicates(self) -> dict[tuple[str, ...], list[tuple[int, dict[str, str]]]]:
        """
        Group duplicate records.

        Returns:
            Dict mapping duplicate key to list of (original_row_number, row_dict)
        """
        groups = defaultdict(list)

        for idx, row in enumerate(self.rows):
            key = tuple(row.get(col, '') for col in self.DUPLICATE_KEY_COLUMNS)
            groups[key].append((idx, row))

        # Filter to only duplicates (2+ rows)
        duplicates = {k: v for k, v in groups.items() if len(v) > 1}

        return duplicates

    def score_record(self, row: dict[str, str]) -> tuple[int, int]:
        """
        Score a record for selection priority.

        Returns:
            Tuple of (source_priority, completeness_score)
        """
        # Score based on source
        source = row.get('Источник', '')  # i18n: content — names.csv's column
        source_priority = 0

        for keyword, priority in self.SOURCE_PRIORITY.items():
            if keyword in source:
                source_priority = max(source_priority, priority)

        # Score based on completeness (number of non-empty fields)
        completeness = sum(1 for v in row.values() if v)

        return (source_priority, completeness)

    def merge_records(self, group: list[tuple[int, dict[str, str]]]) -> dict[str, str]:
        """
        Merge duplicate records by selecting best and filling missing fields.

        Args:
            group: List of (row_index, row_dict) for duplicate records

        Returns:
            Merged record
        """
        # Sort by score (descending)
        scored = [(self.score_record(row), idx, row) for idx, row in group]
        scored.sort(reverse=True)

        # Start with the best record
        best_record = scored[0][2].copy()

        # Fill in missing fields from other records
        for _score, _idx, row in scored[1:]:
            for field, value in row.items():
                # If field is empty in best record but filled in this record, use it
                if not best_record[field] and value:
                    best_record[field] = value

        return best_record

    def remove_duplicates(self) -> tuple[int, int, list[str]]:
        """
        Remove duplicates from loaded rows.

        Returns:
            Tuple of (groups_merged, records_removed, merged_names)
        """
        duplicates = self.group_duplicates()

        if not duplicates:
            return (0, 0, [])

        # Track which rows to remove
        rows_to_remove = set()
        merged_names = []

        for key, group in duplicates.items():
            name = key[1]  # Имя is second element in key
            merged_names.append(f"{name} ({len(group)} → 1)")

            # Merge the records
            merged = self.merge_records(group)

            # Replace the first occurrence with merged record
            first_idx = group[0][0]
            self.rows[first_idx] = merged

            # Mark subsequent occurrences for removal
            for idx, _row in group[1:]:
                rows_to_remove.add(idx)

        # Remove duplicates (in reverse order to preserve indices)
        for idx in sorted(rows_to_remove, reverse=True):
            del self.rows[idx]

        groups_merged = len(duplicates)
        records_removed = len(rows_to_remove)

        return (groups_merged, records_removed, merged_names)

    def write_csv(self, output_path: str | None = None) -> None:
        """Write deduplicated CSV file."""
        out_path = output_path or self.csv_path

        with open(out_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv_dict_writer(f, self.fieldnames)
            writer.writeheader()
            writer.writerows(self.rows)

    def generate_report(
        self,
        groups_merged: int,
        records_removed: int,
        merged_names: list[str]
    ) -> str:
        """Generate markdown report of deduplication."""
        report = []
        report.append("# Duplicate Removal Report\n")
        report.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        report.append("## Summary\n")
        report.append(f"- **Duplicate groups merged:** {groups_merged}")
        report.append(f"- **Records removed:** {records_removed}")
        report.append(f"- **Records remaining:** {len(self.rows)}")
        report.append(f"- **Backup created:** {self.backup_path}")

        if merged_names:
            report.append("\n## Merged Names\n")
            for name in sorted(merged_names):
                report.append(f"- {name}")

        return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(
        description="Remove duplicate records from names.csv with smart merging"
    )
    parser.add_argument(
        '--csv',
        default=None,
        help="Path to names.csv file (default: the workspace's)"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without modifying files'
    )
    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Skip creating backup file'
    )

    args = parser.parse_args()
    args.csv = args.csv or str(names_csv_path())

    # Initialize remover
    remover = DuplicateRemover(args.csv)

    # Create backup (unless disabled or dry-run)
    if not args.no_backup and not args.dry_run:
        backup_path = remover.create_backup()
        print(f"✓ Backup created: {backup_path}")

    # Load CSV
    remover.load_csv()
    original_count = len(remover.rows)
    print(f"✓ Loaded {original_count} records from {args.csv}")

    # Remove duplicates
    groups_merged, records_removed, merged_names = remover.remove_duplicates()

    if groups_merged == 0:
        print("✓ No duplicates found")
        return 0

    print(f"✓ Merged {groups_merged} duplicate groups")
    print(f"✓ Removed {records_removed} duplicate records")
    print(f"✓ {len(remover.rows)} records remaining ({original_count} → {len(remover.rows)})")

    # Write updated CSV (unless dry-run)
    if not args.dry_run:
        remover.write_csv()
        print(f"✓ Updated {args.csv}")

        # Generate report
        report = remover.generate_report(groups_merged, records_removed, merged_names)
        report_path = f"{args.csv}_dedup_report.md"

        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"✓ Report written to {report_path}")
    else:
        print("\n" + "="*60)
        print("DRY RUN - Changes Preview:")
        print("="*60)
        report = remover.generate_report(groups_merged, records_removed, merged_names)
        print(report)

    return 0


if __name__ == '__main__':
    sys.exit(main())
