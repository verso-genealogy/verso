"""The sweep report must be byte-identical across runs.

`make consolidation-sweep` is triage a human reads and re-reads, and the only
practical way to review a change to the scorer is to diff two sweep runs. Every
set the report path renders or iterates is therefore ordered explicitly: an
unsorted `", ".join(...)` over `t.parents & c.parents`, or an unsorted walk of
`relative_keys(target)` feeding a stable sort, makes the diff noise instead of
signal (62 lines of pure shuffling on Глуповы Горы, ~50 on Заманиловка).

Running the report twice in ONE process proves nothing — a set's iteration order
is fixed for a given interpreter — so the fixture is rendered in subprocesses
under several PYTHONHASHSEED values, which is the same variation two shell runs
of the Makefile target see.
"""
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

from tests.codepaths import child_env
from verso.ru.consolidation import candidates as f

_THIS_FILE = Path(__file__).resolve()

# Enough shared relatives that their rendering order is visibly unstable, and
# two candidates reachable only through DIFFERENT relatives so the order the
# candidate rows themselves arrive in is unstable too.
_FATHER = ("Фома", "Ильич")
_MOTHER = ("Анна", "Ивановна")
_WIFE = ("Марфа", "Зотовна")
_SON_A = ("Иван", "Петрович")
_SON_B = ("Егор", "Петрович")


def _occ(given, patr, *, record_num, year, rec_type="birth", role="father",
         stub=None, children=()):
    return f.Occurrence(
        key=(given, patr), name=f"{given} {patr} Сидоров", given=given, patr=patr,
        surname="Сидоров", gender="male", rec_type=rec_type,
        record_num=record_num, role=role, year=year, source_file="t.py",
        parents={_FATHER, _MOTHER}, spouses={_WIFE}, children=set(children),
        stub=stub,
    )


def _fixture_occurrences():
    target = _occ("Пётр", "Фомич", record_num=1, year=1840, stub="_1840_b1_petr",
                  children=[_SON_A, _SON_B])
    # Shares the blocking key, so the plain pool reaches it.
    same_key = _occ("Пётр", "Фомич", record_num=2, year=1841, stub="_1841_b2_petr",
                    children=[_SON_A, _SON_B])
    # Patronymic variants: reachable ONLY through the relative index, and each
    # through a different child, so which one lands first depends on the order
    # `relative_keys(target)` is walked in.
    via_a = _occ("Пётр", "Филиппович", record_num=3, year=1842,
                 stub="_1842_b3_petr", children=[_SON_A])
    via_b = _occ("Пётр", "Фокич", record_num=4, year=1843,
                 stub="_1843_b4_petr", children=[_SON_B])
    return target, [target, same_key, via_a, via_b]


def render_fixture_report() -> str:
    """The sweep's report path over a fixed set of occurrences.

    Mirrors `main(--sweep)`: exact-key pool + per-given-name relative index,
    `low` candidates dropped, rendered by `preliminary_report`."""
    _target, all_occs = _fixture_occurrences()
    pool_by_key: dict[f.PersonKey, list[f.Occurrence]] = {}
    for o in all_occs:
        pool_by_key.setdefault(o.key, []).append(o)
    rel_index: dict[f.PersonKey, list[f.Occurrence]] = {}
    for o in all_occs:
        for r in f.relative_keys(o):
            rel_index.setdefault(r, []).append(o)
    results = []
    for t in all_occs:
        local = [s for s in f.find_local_candidates(t, pool_by_key, set(),
                                                    rel_index=rel_index)
                 if s.confidence != "low"]
        if not local:
            continue
        results.append({
            "target": t.public(),
            "local": [{"confidence": s.confidence, "score": s.score,
                       "evidence": s.evidence, "cand": s.cand.public()} for s in local],
            "geni": [],
        })
    assert results, "fixture produced no candidates — it no longer tests anything"
    return f.preliminary_report(results)


def _render_under_hash_seed(seed: int) -> str:
    code = textwrap.dedent(f"""
        import importlib.util, sys
        spec = importlib.util.spec_from_file_location("_sweep_fixture", {str(_THIS_FILE)!r})
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.stdout.write(mod.render_fixture_report())
    """)
    env = child_env(PYTHONHASHSEED=str(seed))
    proc = subprocess.run([sys.executable, "-c", code], env=env,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(f"fixture render failed under seed {seed}:\n{proc.stderr}")
    return proc.stdout


class TestSweepReportIsByteStable(unittest.TestCase):
    def test_report_is_identical_under_every_hash_seed(self):
        baseline = _render_under_hash_seed(0)
        for seed in range(1, 12):
            self.assertEqual(baseline, _render_under_hash_seed(seed),
                             f"sweep report differs under PYTHONHASHSEED={seed}")

    def test_shared_relative_evidence_is_sorted(self):
        target, all_occs = _fixture_occurrences()
        s = f.score_pair(target, all_occs[1])
        parents = next(e for e in s.evidence if e.startswith("shared parent: "))
        names = parents.removeprefix("shared parent: ").split(", ")
        self.assertEqual(names, sorted(names))
        children = next(e for e in s.evidence if e.startswith("shared child: "))
        names = children.removeprefix("shared child: ").split(", ")
        self.assertEqual(names, sorted(names))


if __name__ == "__main__":
    unittest.main()
