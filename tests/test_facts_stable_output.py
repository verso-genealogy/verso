"""The facts layer's reports must be byte-identical across runs.

The layer's documentation has said so since it landed; nothing enforced it. A report a
human diffs — `check-godparent-cooccurrence`, `death-age-check`,
`facts-check check=date-order|birth-claims|father-claims|death-claims` — is only reviewable when two runs
of unchanged input print the same bytes, and the committed findings snapshot
(`facts_findings.tsv`) is only a ratchet if its counts cannot wobble.

Running a report twice in ONE process proves nothing — a set's iteration order
is fixed for a given interpreter — so the fixture is rendered in subprocesses
under several PYTHONHASHSEED values, the variation two shell runs of a Makefile
target actually see. Same method as `tests/test_candidates_stable_output.py`.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
import unittest
from calendar import Month
from pathlib import Path
from typing import Any

from tests.codepaths import child_env

_THIS_FILE = Path(__file__).resolve()


def _births() -> list[Any]:
    """Two families whose godparents recur, each pair the same size, so the
    order of equal-count pairs is exactly what a hash seed could shuffle; and
    a child a later burial states the wrong age for."""
    from verso.ru.domain import person
    from verso.ru.dsl.records.births import birth, birth_month, birth_records
    from verso.ru.gender import Gender

    def b(num: int, day: int, father: tuple[str, str], gp: tuple[str, str, str],
          child: str = "Иван") -> Any:
        return birth(num, Gender.FEMALE if child == "Анна" else Gender.MALE, day, day,
                     child=person(child), father=person(*father),
                     mother=person("Мария", "Петрова"),
                     god_parent1=person(gp[0], gp[1], last_name_orig=gp[2]))

    out = []
    for year, first in ((1840, 1), (1841, 10), (1842, 20)):
        book = birth_records("A", "1", "1", "1", "Тестовка", "Никольская", year,
                             *birth_month(Month.MARCH,
                                          b(first, 3, ("Петр", "Иванов"),
                                            ("Семен", "Ильин", "Сидоров")),
                                          b(first + 1, 4, ("Фома", "Лукин"),
                                            ("Яков", "Пименов", "Суетливцев")),
                                          b(first + 2, 5, ("Павел", "Андреев"),
                                            ("Лука", "Ильин", "Хмурин"),
                                            child="Анна")))
        out.append((book, f"{year}/births_{year}.py"))
    return out


def _deaths() -> list[Any]:
    from verso.ru.domain import person
    from verso.ru.dsl.records.deaths import death, death_month, death_records
    from verso.ru.gender import Gender
    from verso.ru.relationship import Relationship, relative

    book = death_records("A", "1", "1", "1", "Тестовка", "Никольская", 1842,
                         *death_month(Month.JULY,
                                      death(1, Gender.FEMALE, 20, 20, Month.JULY,
                                            Month.JULY, deceased=person("Анна"),
                                            age=4, relatives=[relative(
                                                person("Павел", "Андреев"),
                                                Relationship.FATHER)])))
    return [(book, "1842/deaths_1842.py")]


def _second_burial() -> list[Any]:
    """Another Анна Павловна, buried ten days before the fixture's and with no
    burial day: two deaths of one name, which `death-claims` reads apart."""
    from verso.ru.domain import person
    from verso.ru.dsl.records.deaths import death, death_records
    from verso.ru.gender import Gender
    from verso.ru.relationship import Relationship, relative

    book = death_records("A", "1", "1", "1", "Тестовка", "Никольская", 1842,
                         death(2, Gender.FEMALE, 10, None, Month.JULY, None,
                               deceased=person("Анна"), age=4, relatives=[relative(
                                   person("Павел", "Андреев"), Relationship.FATHER)]))
    return [(book, "1842/deaths_1842b.py")]


def _reconcile_report(births: Any) -> str:
    """The reconciliation channel over the fixture's births and a 1917 list
    naming two of its godparents — each appearance its own person, so each
    entry has three namesakes whose order a seed could shuffle."""
    from verso.ru.consolidation.reconcile import format_report as reconcile_report
    from verso.ru.domain import person
    from verso.ru.dsl.records.name_lists import listed_person, name_list_records
    from verso.ru.facts.checks.reconcile import reconcile
    from verso.ru.facts.extract.name_lists import facts_from_name_lists
    from verso.ru.facts.model import AssertionSet

    roster = name_list_records(
        "A", "1", "1", "1", "Тестовка", 1917,
        listed_person(1, person("Семенъ", "Ильинъ", "Сидоровъ"), age=77),
        listed_person(2, person("Яковъ", "Пименовъ", "Суетливцевъ")),
        document_type="Список избирателей")
    facts = AssertionSet(list(births) + list(facts_from_name_lists(
        [(roster, "1917/list.py")], village="Тестовка")))

    def own_key(who: object) -> tuple[str]:
        return (str(who),)

    def alone(_record: Any) -> Any:
        return own_key
    return reconcile_report(reconcile(facts, alone), {}, all_targets=True)


def render_fixture_reports() -> str:
    """Every facts report whose order a set could decide, over one fixture."""
    from verso.ru.cli.facts import (
        format_birth_claims, format_death_claims, format_father_claims, format_report, run)
    from verso.ru.facts.checks.deaths import death_claims
    from verso.ru.facts.extract.deaths import facts_from_deaths
    from verso.ru.facts.checks.fathers import father_findings
    from verso.ru.facts.checks.births import birth_claims_of, birth_pairs
    from verso.ru.consolidation.death_age import find_death_age_conflicts
    from verso.ru.consolidation.death_age import format_report as death_report
    from verso.ru.facts.extract.births import facts_from_births
    from verso.ru.facts.identity import canonical_fold, name_identity
    from verso.ru.facts.model import AssertionSet

    births = _births()
    items = []
    for book, source in births:
        for rec in book.records:
            if rec.year is None:
                rec.year = book.year
            items.append((rec, source))
    facts = AssertionSet(facts_from_births(items, village="Тестовка"))

    parts = [format_report(run(facts, min_count=2), 2, None)]
    parts.append(death_report(find_death_age_conflicts(_births(), _deaths())))
    assert birth_pairs()
    found = birth_claims_of(facts.believed(), name_identity(canonical_fold))
    parts.append(format_birth_claims(found, lambda res_name: res_name))
    parts.append(_reconcile_report(facts))
    fathers = father_findings(facts.believed(), name_identity(canonical_fold))
    parts.append(format_father_claims(fathers, lambda res_name: res_name))
    burials = [(rec, source) for book, source in _deaths() + _second_burial()
               for rec in book.records]
    for rec, _ in burials:
        rec.year = rec.year or 1842
    buried = AssertionSet(facts_from_deaths(burials, village="Тестовка")).believed()
    parts.append(format_death_claims(death_claims(buried, name_identity(canonical_fold)),
                                     lambda res_name: res_name))
    report = "\n\n".join(parts)
    assert "Суетливцев" in report and "death-age-check: 1 finding" in report \
        and "среди" not in report and "[AMBIGUOUS]" in report \
        and "записей 3: отец Петр" in report and "разрыв 10 дн." in report, \
        "fixture no longer exercises the reports it is here for"
    return report


def _render_under_hash_seed(seed: int) -> str:
    code = textwrap.dedent(f"""
        import importlib.util, sys
        spec = importlib.util.spec_from_file_location("_facts_fixture", {str(_THIS_FILE)!r})
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.stdout.write(mod.render_fixture_reports())
    """)
    env = child_env(PYTHONHASHSEED=str(seed))
    proc = subprocess.run([sys.executable, "-c", code], env=env,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(f"fixture render failed under seed {seed}:\n{proc.stderr}")
    return proc.stdout


class FactsReportsAreByteStable(unittest.TestCase):
    def test_reports_are_identical_under_every_hash_seed(self):
        baseline = _render_under_hash_seed(0)
        for seed in range(1, 8):
            self.assertEqual(baseline, _render_under_hash_seed(seed),
                             f"facts reports differ under PYTHONHASHSEED={seed}")


if __name__ == "__main__":
    unittest.main()
