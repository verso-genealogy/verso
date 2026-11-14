#!/usr/bin/env python3
"""Fix: split 'Name Patronymic' stored as one string into separate name_orig + patr_orig/patr_old fields."""

import ast
import sys
from pathlib import Path

from verso.ru.naming import modernize_orthography, validate_first_name

MODERN_SUFFIXES = ('ович', 'евич', 'ич', 'овна', 'евна', 'ична', 'ишна')  # i18n: content — patronymic endings: vocabulary


def is_modern_patronymic(s):
    return isinstance(s, str) and any(s.endswith(sfx) for sfx in MODERN_SUFFIXES)


def should_split(combined):
    """Return (name, patr) if combined is exactly 'Name Patronymic' (one space), else None."""
    if not isinstance(combined, str) or combined.count(' ') != 1:
        return None
    name, patr = combined.split(' ')
    if not validate_first_name(modernize_orthography(name)):
        return None
    return name, patr


def collect_fixes(tree):
    """Return list of (line_idx, byte_start, byte_end, replacement_bytes)."""
    fixes = []

    class Visitor(ast.NodeVisitor):
        def visit_Call(self, node):
            if getattr(node.func, 'id', None) == 'person':
                # name_orig is the first positional arg
                if node.args:
                    name_arg = node.args[0]
                    if isinstance(name_arg, ast.Constant):
                        result = should_split(name_arg.value)
                        if result:
                            name, patr = result
                            # Ensure no existing patr_orig at position 1 (positional)
                            has_patr_orig = (len(node.args) > 1) or any(
                                kw.arg == 'patr_orig' for kw in node.keywords
                            )
                            assert not has_patr_orig, (
                                f"Line {name_arg.lineno}: patr_orig already present, manual fix needed"
                            )

                            line_idx = name_arg.lineno - 1
                            byte_start = name_arg.col_offset
                            byte_end = name_arg.end_col_offset

                            # Build replacement: encode in UTF-8 to match byte positions
                            name_bytes = name.encode('utf-8')
                            patr_bytes = patr.encode('utf-8')

                            if is_modern_patronymic(patr):
                                replacement = b'"' + name_bytes + b'", patr_old="' + patr_bytes + b'"'
                            else:
                                replacement = b'"' + name_bytes + b'", "' + patr_bytes + b'"'

                            fixes.append((line_idx, byte_start, byte_end, replacement))

            self.generic_visit(node)

    Visitor().visit(tree)
    return fixes


def fix_file(path, dry_run=False):
    source = path.read_text(encoding='utf-8')
    lines = source.split('\n')
    tree = ast.parse(source)

    fixes: list[tuple[int, int, int, bytes]] = collect_fixes(tree)
    if not fixes:
        return 0

    # Sort by line then descending byte position to avoid offset shifts
    fixes.sort(key=lambda x: (x[0], -x[1]))

    line_bytes_list = [line.encode('utf-8') for line in lines]

    for line_idx, byte_start, byte_end, replacement in fixes:
        lb = line_bytes_list[line_idx]
        removed = lb[byte_start:byte_end].decode('utf-8')
        if dry_run:
            print(f"{path}:{line_idx+1}: {removed!r} → {replacement.decode('utf-8')!r}")
        line_bytes_list[line_idx] = lb[:byte_start] + replacement + lb[byte_end:]

    if not dry_run:
        path.write_bytes(b'\n'.join(line_bytes_list))

    return len(fixes)


def main():
    dry_run = '--dry-run' in sys.argv
    paths = [Path(a) for a in sys.argv[1:] if not a.startswith('--')]
    total = 0
    for p in paths:
        if p.is_file() and p.suffix == '.py':
            count = fix_file(p, dry_run=dry_run)
            if count:
                print(f"{p}: fixed {count} name(s)")
            total += count
    print(f"Total: {total} fix(es)")


if __name__ == '__main__':
    main()
