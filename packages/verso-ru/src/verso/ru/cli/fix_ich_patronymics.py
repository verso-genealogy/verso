#!/usr/bin/env python3
"""Fix: remove explicit modern-form patronymic from deceased/child when father is specified."""

import ast
import sys
from pathlib import Path


def is_modern_patronymic(s):
    """True for modern canonical patronymics (male: *ич; female: *овна/*евна/*ична/*ишна)."""
    return isinstance(s, str) and (
        s.endswith('ич')  # i18n: content — patronymic endings: vocabulary
        or s.endswith('овна') or s.endswith('евна')  # i18n: content — patronymic endings: vocabulary
        or s.endswith('ична') or s.endswith('ишна')  # i18n: content — patronymic endings: vocabulary
    )


def get_patr_orig_node(person_node):
    """Return (node, 'positional') for the patr_orig arg, or (None, None)."""
    for kw in person_node.keywords:
        if kw.arg == 'patr_orig':
            return kw.value, 'keyword'
    if len(person_node.args) > 1:
        return person_node.args[1], 'positional'
    return None, None


def has_father_in_call(call_node):
    """True if death()/birth() call specifies a father."""
    for kw in call_node.keywords:
        if kw.arg == 'father':
            return True
        if kw.arg == 'relatives' and isinstance(kw.value, ast.List):
            for elt in kw.value.elts:
                if not (isinstance(elt, ast.Call) and getattr(elt.func, 'id', None) == 'relative'):
                    continue
                rel = elt.args[1] if len(elt.args) > 1 else next(
                    (k.value for k in elt.keywords if k.arg == 'relationship'), None)
                if isinstance(rel, ast.Attribute) and rel.attr == 'FATHER':
                    return True
    return False


def collect_deletions(tree):
    """Return list of (line_idx, col_start, col_end) for patr_orig args to remove."""
    deletions = []

    class Visitor(ast.NodeVisitor):
        def visit_Call(self, node):
            func_name = getattr(node.func, 'id', None)
            if func_name in ('death', 'birth'):
                for kw in node.keywords:
                    if kw.arg in ('deceased', 'child'):
                        pnode = kw.value
                        if (isinstance(pnode, ast.Call)
                                and getattr(pnode.func, 'id', None) == 'person'):
                            patr_node, kind = get_patr_orig_node(pnode)
                            if (patr_node is not None
                                    and isinstance(patr_node, ast.Constant)
                                    and is_modern_patronymic(patr_node.value)
                                    and has_father_in_call(node)):
                                if kind == 'positional':
                                    line_idx = patr_node.lineno - 1
                                    # Remove the leading ", " + arg text
                                    col_start = patr_node.col_offset - 2
                                    col_end = patr_node.end_col_offset
                                    deletions.append((line_idx, col_start, col_end))
                                # keyword patr_orig= not seen in practice; skip
            self.generic_visit(node)

    Visitor().visit(tree)
    return deletions


def fix_file(path, dry_run=False):
    source = path.read_text(encoding='utf-8')
    lines = source.split('\n')
    tree = ast.parse(source)
    deletions: list[tuple[int, int, int]] = collect_deletions(tree)
    if not deletions:
        return 0

    # Sort by line then descending col so later edits don't shift earlier positions
    deletions.sort(key=lambda x: (x[0], -x[1]))

    # AST col_offset is a UTF-8 byte offset; work in bytes for slicing
    line_bytes_list = [line.encode('utf-8') for line in lines]

    for line_idx, col_start, col_end in deletions:
        lb = line_bytes_list[line_idx]
        removed = lb[col_start:col_end].decode('utf-8')
        assert lb[col_start:col_start + 2] == b', ', (
            f"{path}:{line_idx+1}: expected b', ' before byte {col_start}, "
            f"got {lb[col_start:col_start+2]!r}"
        )
        if dry_run:
            print(f"{path}:{line_idx+1}: remove {removed!r}")
        line_bytes_list[line_idx] = lb[:col_start] + lb[col_end:]

    if not dry_run:
        path.write_bytes(b'\n'.join(line_bytes_list))

    return len(deletions)


def main():
    dry_run = '--dry-run' in sys.argv
    paths = [Path(a) for a in sys.argv[1:] if not a.startswith('--')]
    total = 0
    for p in paths:
        if p.is_file() and p.suffix == '.py':
            count = fix_file(p, dry_run=dry_run)
            if count:
                print(f"{p}: fixed {count} patronymic(s)")
            total += count
    print(f"Total: {total} fix(es)")


if __name__ == '__main__':
    main()
