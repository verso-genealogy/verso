"""An entry its book left unnumbered is said «без номера» in every report — never «№none», never a bare «none».

The extractors write such an entry's `record_num` as "none" (`verso.ru.facts.extract.common`); a report names a
record by `verso.ru.facts.labels.record_number`, and no line of the library writes the number itself.
"""
from __future__ import annotations

import ast
from pathlib import Path

import tomllib

from verso.core import i18n
from verso.ru.facts.labels import record_number
from verso.ru.facts.model import Citation
from verso.ru.messages import t

SOURCE = Path(__file__).resolve().parent.parent / "packages" / "verso-ru" / "src" / "verso" / "ru"


def _cite(number: str) -> Citation:
    return Citation(village="Горюхино", source_file="births_1850.py", record_kind="birth", record_num=number, entry=0)


def test_a_number_is_said_with_its_sign_and_none_as_unnumbered():
    assert record_number(_cite("7")) == "№7" and record_number(_cite("7"), sign=False) == "7"
    assert record_number(_cite("none")) == record_number(_cite("none"), sign=False) == str(t("cli.facts.unnumbered"))
    assert i18n.render(t("cli.facts.unnumbered"), "ru") == "без номера"
    assert i18n.render(t("cli.facts.unnumbered"), "en") == "unnumbered"


#: Where a line may write a `record_num` itself, each with its reason.
WRITES_ITS_OWN = {
    "facts/model.py": "`Citation.number`, the one place a citation's number is said",
    "consolidation/stale_claims.py": "a DSL record's own number, «?» where it has none — no citation's",
    "consolidation/sibling_spacing.py": "the same",
    "facts/extract/common.py": "a persona's key (`file#entry:year:number`), no reader's line",
    "cli/show_record.py": "the number the user asked for, said back",
}
#: The packages whose lines a reader reads as a report; the translator's numbers name Terraform resources and Geni's
#: documents, which no report prints.
REPORTS = ("facts", "consolidation", "cli")


def _writes_a_number(tree: ast.AST) -> list[int]:
    """The lines that put a `record_num` into text: an f-string, a `+` or `%` with a text, a `.format(…)`, or a
    message's `number=` — every way a report once printed «№none» or «рек. none»."""
    def holds(node: ast.AST) -> bool:
        return any(isinstance(sub, ast.Attribute) and sub.attr == "record_num" for sub in ast.walk(node))

    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr) and holds(node):
            lines.append(node.lineno)
        elif (isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)) and holds(node)
              and any(isinstance(side, (ast.Constant, ast.JoinedStr)) and isinstance(getattr(side, "value", ""), str)
                      for side in (node.left, node.right))):
            lines.append(node.lineno)
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format"
              and any(holds(a) for a in [*node.args, *(k.value for k in node.keywords)])):
            lines.append(node.lineno)
        elif isinstance(node, ast.keyword) and node.arg == "number" and holds(node.value):
            lines.append(node.value.lineno)
    return sorted(set(lines))


def test_no_line_of_the_library_writes_a_record_s_number_itself():
    """Each report once wrote «№{…record_num}» (or «рек. {…record_num}») on its own and printed «№none» for an
    unnumbered entry; a citation says its number through `Citation.number` (`record_number`)."""
    found = [f"{rel}:{n}" for package in REPORTS for path in (SOURCE / package).rglob("*.py")
             if (rel := path.relative_to(SOURCE).as_posix()) not in WRITES_ITS_OWN
             for n in _writes_a_number(ast.parse(path.read_text(encoding="utf-8")))]
    assert found == []


def test_the_guard_sees_every_way_a_number_was_written():
    for src in ('f"№{c.record_num}"', 'f"рек. {cite.record_num}"', '"№" + c.record_num', '"№%s" % c.record_num',
                '"№{}".format(c.record_num)', 't("key", number=c.record_num)'):
        assert _writes_a_number(ast.parse(src)) == [1], src
    assert _writes_a_number(ast.parse("c.record_num == 'none'")) == []
    assert _writes_a_number(ast.parse("sorted(x, key=lambda c: c.record_num)")) == []


def test_a_citation_says_its_number_in_every_line_that_names_it():
    """`str(cite)` (the lines of `verso facts --why`) as well as a report's."""
    assert "none" not in str(_cite("none")) and f"рек. {t('cli.facts.unnumbered')}," in str(_cite("none"))
    assert "рек. 7," in str(_cite("7"))


#: The templates that may write «№{number}», each with its reason.
SIGNED = {
    "cli.facts.lags.finding": "called by nothing since 0.1.45, kept until 0.2 (tests/test_catalog_ru.py)",
    "consolidation.reconcile.backing": "a list neighbour's number, an int: an unnumbered entry has no neighbours",
    "consolidation.reconcile.backing_by_name": "the same",
}


def _templates(tree: dict[str, object], prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in tree.items():
        if isinstance(value, dict) and not ({"one", "other"} & set(value)):
            out |= _templates(value, f"{prefix}{key}.")
        else:
            out[prefix + key] = str(value)
    return out


def test_no_message_writes_the_sign_before_a_number_it_is_handed():
    """A template that writes «№{number}» prints «№none» when handed an unnumbered entry's number."""
    for path in (SOURCE / "locales").glob("*.toml"):
        signed = {key for key, text in _templates(tomllib.loads(path.read_text(encoding="utf-8"))).items()
                  if "№{number}" in text}
        assert signed == set(SIGNED), path.name
