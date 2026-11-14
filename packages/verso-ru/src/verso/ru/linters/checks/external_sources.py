#!/usr/bin/env python3
"""AST-based linter for external-source DSL records (`criminal_record()` /
`wwi_record()` / `wwii_record()` from verso.ru.dsl).

ESC001 — `source_url` host must match the record kind. A судимость record links
to the Familio criminal-gazette catalog (`familio.org/catalogs/vss/...`) or the
RSL digitised-gazette viewer (`viewer.rsl.ru/...`) the scan is re-hosted from;
a WWI record links to a gwar.mil.ru hero card (`gwar.mil.ru/...`); a WWII
record links to a pamyat-naroda.ru / podvignaroda.ru / obd-memorial.ru card.
A mismatched host almost always means the wrong verb (a gwar card filed as a
судимость, or vice versa).

ESC002 — `original_text` (the verbatim gazette entry) must be non-empty on a
`criminal_record()`; it is the proof the document carries in its description.

ESC003 — `casualty_reason` («причина выбытия») must not be set on a `wwi_record()`
or `wwii_record()` whose `document_type` is an award document: an award
records a decoration, not a casualty, so a причина выбытия there is a mistake
(usually copy-pasted from a neighbouring casualty card).

ESC004 — `award` («награда») / `award_number` («Номер награждения») may only be
set on a `wwi_record()`/`wwii_record()` whose `document_type` is an award
document. An award field on a casualty/wounded/POW card is the mirror image of
ESC003: a decoration belongs only on an award document, so the document_type
must be one of the award members (`WwiDocumentType.AWARD_LISTS`, or the WWII
`WwiiDocumentType.NAGRADNOY_LIST`/`AWARD_ORDER`/`ANNIVERSARY_AWARD`).

Path-independent: scopes purely on the call func name, so it behaves the same
whether linting the file on disk or a temp-file copy of an unsaved editor
buffer.

Run:
    python3 -m verso.ru.linters.checks.external_sources FILE [FILE...]
"""

import ast
import sys
from pathlib import Path
from typing import Any

from verso.ru.dsl.records.external_sources import WwiDocumentType, WwiiDocumentType
from verso.ru.linters.issue import says
from verso.ru.linters.checks import shared_ast

# Accepted source_url hosts per kind. A судимость links either to the Familio
# vss catalog page or to the RSL viewer the scan is re-hosted from (record-only
# vss entries have no Familio person page, so the RSL link is the canonical proof
# URL).
CRIMINAL_HOSTS = ("familio.org/catalogs/vss", "viewer.rsl.ru")
GWAR_HOSTS = ("gwar.mil.ru",)
PAMYAT_HOSTS = ("pamyat-naroda.ru", "podvignaroda.ru", "obd-memorial.ru")

# Enum member *names* whose document is an award (WWI «Списки награжденных»;
# WWII наградной лист/приказ о награждении/юбилейная картотека), where
# casualty_reason is meaningless. Derived from the enums so it stays in sync.
AWARD_MEMBER_NAMES = frozenset(
    m.name for m in WwiDocumentType if m.is_award
) | frozenset(
    m.name for m in WwiiDocumentType if m.is_award
)


def _call_func_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _kwargs(node: ast.Call) -> dict[str, ast.keyword]:
    return {kw.arg: kw for kw in node.keywords if kw.arg is not None}


def _str_literal(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_none_literal(node: ast.expr | None) -> bool:
    """True for an explicit `None` literal (so `award=None` is treated as unset)."""
    return isinstance(node, ast.Constant) and node.value is None


def _enum_member_name(node: ast.expr | None) -> str | None:
    """The trailing attribute of an enum reference, e.g. the `AWARD_LISTS` of
    `WwiDocumentType.AWARD_LISTS`. Returns None for anything else."""
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def check_file_structured(path: Path) -> list[dict[str, Any]]:
    try:
        src = path.read_text(encoding="utf-8")
        tree = shared_ast.parse(src)
    except SyntaxError:
        return []

    issues: list[dict[str, Any]] = []
    for node in shared_ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fname = _call_func_name(node)
        if fname not in ("criminal_record", "wwi_record", "wwii_record"):
            continue
        kw = _kwargs(node)

        url_kw = kw.get("source_url")
        if url_kw is not None:
            url = _str_literal(url_kw.value)
            if fname == "criminal_record":
                hosts = CRIMINAL_HOSTS
            elif fname == "wwi_record":
                hosts = GWAR_HOSTS
            else:
                hosts = PAMYAT_HOSTS
            if url is not None and not any(h in url for h in hosts):
                expected = " or ".join(f"'{h}'" for h in hosts)
                issues.append({
                    "level": "error",
                    "line": url_kw.value.lineno,
                    **says("ESC001", "host", expected=expected, func=fname, url=repr(url)),
                })

        if fname in ("wwi_record", "wwii_record"):
            dt_kw = kw.get("document_type")
            cr_kw = kw.get("casualty_reason")
            if dt_kw is not None and cr_kw is not None:
                member = _enum_member_name(dt_kw.value)
                cr = _str_literal(cr_kw.value)
                if member in AWARD_MEMBER_NAMES and (cr is None or cr.strip()):
                    issues.append({
                        "level": "error",
                        "line": cr_kw.value.lineno,
                        **says("ESC003", "award", member=member),
                    })

            # ESC004 — award fields require an award document_type.
            dt_member = _enum_member_name(dt_kw.value) if dt_kw is not None else None
            is_award_doc = dt_member in AWARD_MEMBER_NAMES
            for arg_name in ("award", "award_number"):     # «награда», «Номер награждения»: the catalog's
                aw_kw = kw.get(arg_name)
                if aw_kw is None or _is_none_literal(aw_kw.value):
                    continue
                if not is_award_doc:
                    doc = "typed" if dt_member is not None else "untyped"
                    issues.append({
                        "level": "error",
                        "line": aw_kw.value.lineno,
                        **says("ESC004", f"{arg_name}_{doc}", **({"member": dt_member} if dt_member is not None else {})),
                    })

        if fname == "criminal_record":
            ot_kw = kw.get("original_text")
            if ot_kw is not None:
                ot = _str_literal(ot_kw.value)
                if ot is not None and not ot.strip():
                    issues.append({
                        "level": "error",
                        "line": ot_kw.value.lineno,
                        **says("ESC002", "empty"),
                    })
    return issues


def check_file(path: Path) -> list[str]:
    return [
        f"{path}:{i['line']}: {i['message']}"
        for i in check_file_structured(path)
    ]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    all_errors: list[str] = []
    for arg in sys.argv[1:]:
        all_errors.extend(check_file(Path(arg)))
    for e in all_errors:
        print(e)
    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())
