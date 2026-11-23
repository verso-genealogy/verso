#!/usr/bin/env python3
"""Unified DSL linter wrapper — runs all DSL linters and outputs unified JSON."""

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import verso.ru.linters.checks.single_line_calls as check_single_line_calls
import verso.ru.linters.checks.genders as check_genders
import verso.ru.linters.checks.names as check_names
import verso.ru.linters.checks.relationship_ref as check_relationship_ref
import verso.ru.linters.checks.ages as check_ages
import verso.ru.linters.checks.hidden_flag as check_hidden_flag
import verso.ru.linters.checks.parent_member as check_parent_member
import verso.ru.linters.checks.birth_redundancy as check_birth_redundancy
import verso.ru.linters.checks.census_redundancy as check_census_redundancy
import verso.ru.linters.checks.census_status_redundancy as check_census_status_redundancy
import verso.ru.linters.checks.status_redundancy as check_status_redundancy
import verso.ru.linters.checks.relative_attachment as check_relative_attachment
import verso.ru.linters.checks.residence_title as check_residence_title
import verso.ru.linters.checks.unmapped_location as check_unmapped_location
import verso.ru.linters.checks.external_sources as check_external_sources
import verso.ru.linters.checks.name_lists as check_name_lists
import verso.ru.linters.checks.patronymic_form as check_patronymic_form
import verso.ru.linters.checks.name_gender_agreement as check_name_gender_agreement
import verso.ru.linters.checks.marital_status as check_marital_status
import verso.ru.linters.checks.census_age as check_census_age
import verso.ru.linters.checks.census_member_lines as check_census_member_lines
import verso.ru.linters.checks.census_parent_link as check_census_parent_link
import verso.ru.linters.checks.deaths_residence as check_deaths_residence
import verso.ru.linters.checks.deaths_relatives as check_deaths_relatives
import verso.ru.linters.checks.deaths_burial_date as check_deaths_burial_date
import verso.ru.linters.checks.parent_status as check_parent_status
import verso.ru.linters.checks.marriage_residence as check_marriage_residence
import verso.ru.linters.checks.reviewed_redundancy as check_reviewed_redundancy
import verso.ru.linters.checks.retractions as check_retractions
import verso.ru.linters.checks.witness_side as check_witness_side
import verso.ru.linters.checks.civil_register as check_civil_register
import verso.ru.linters.checks.status_orthography as check_status_orthography
import verso.ru.linters.checks.dsl_imports as check_dsl_imports
from verso.ru.linters.issue import as_dict, issue
from verso.ru.messages import t
from verso.ru.linters.checks import shared_ast

def _check_single_line_calls_structured(path: Path) -> list[dict[str, Any]]:
    """Run check_single_line_calls using Checker directly for structured fix data."""
    issues = []
    try:
        source = path.read_text()
        tree = shared_ast.parse(source)
        checker = check_single_line_calls.Checker(source)
        checker.visit(tree)

        # Multi-line violations — no fix
        for start, end, name in checker.violations:
            issues.append({"level": "error", "line": start, **check_single_line_calls.spans(name, start, end)})

        # Constant violations — fix: replace string literal with constant.
        # `col` disambiguates which occurrence when a line has several matching
        # kwargs (0-based char column where `kw_arg=` starts).
        for line, kw_arg, literal, const_name, col in checker.const_violations:
            issues.append({
                "level": "error",
                "line": line,
                **check_single_line_calls.use_constant(kw_arg, literal, const_name),
                "fix": {
                    "type": "replace_kwarg",
                    "kwarg": kw_arg,
                    "old": f'"{literal}"',
                    "new": const_name,
                    "col": col,
                },
            })

        # Redundant violations — fix: remove kwarg. `col` pins the exact kwarg
        # occurrence (a line may carry several `status=`/`residence=` kwargs).
        for (line, _func_name, _message, col), (said, kwarg) in zip(checker.redundant_violations,
                                                                   checker.redundant_said, strict=True):
            issues.append({"level": "error", "line": line, **said,
                           "fix": {"type": "remove_kwarg", "kwarg": kwarg, "col": col}})

    except SyntaxError as e:
        issues.append(as_dict(issue("SYN001", "bare", e.lineno or 1, level="error")))
    return issues


@dataclass(frozen=True)
class Linter:
    """One registered DSL check.

    `structured` feeds --json mode (issue dicts, may carry fix metadata);
    `plain` feeds text mode ('path:line: message' strings). Advisory linters
    print as warnings in text mode and never affect the exit code / fail CI.
    """
    name: str
    structured: Callable[[Path], list[dict[str, Any]]]
    plain: Callable[[Path], list[str]]
    advisory: bool = False


# census_redundancy and census_status_redundancy are advisory-in-text-mode on
# purpose: they surface in the IDE as errors (with remove quick-fixes) via the
# JSON path, but the census corpus already carries thousands of redundant
# surnames/patronymics (census_redundancy) and per-member statuses that repeat
# the RecordDefaults default (census_status_redundancy), so gating CI on them
# would fail every run. Promote once that bulk cleanup lands. census_age,
# unmapped_location and patronymic_form are advisory by design (heuristic /
# data-dependent), as is census_parent_link (heuristic father-plausibility
# with a three-way resolution — one of them is "keep as-is"). deaths_residence
# is a HARD error since the corpus reached 0 on both codes: the 122 both-sided
# records keep residence on the DECEASED (the record's subject) and the
# relatives' redundant copies were stripped — Death.__init__ derives the
# household value either way, so a new DRA002 is a pointless duplicate and a
# DRA001 a genuine contradiction. NB the IDE still shows DRA002 as a yellow
# warning (per-issue level "warn") while CI fails on it — the quick fix makes
# it a one-click cleanup. marriage_residence (MRA001) is hard from birth: it
# fires only on two EXPLICIT, differing residences for a party and their own
# parent (0 corpus findings — pure drift protection); implicit sides are never
# compared because Marriage deliberately has no residence inheritance (clergy
# genuinely live across parishes). parent_status (PSA001-PSA003) is HARD
# since 2026-09-26, when the corpus reached 0: free-text statuses are read by
# estate_of (+28 found, all stated), the out-of-scope parents' children
# (мещане/купцы/помещики/дворовые) were given their child forms, a landlord's
# дворовый and крестьянин count as one estate (the maintainers' call), and the last
# two PSA001 were read on the scans — both misread owners. A new finding is a
# regression caught while authoring, not debt. PSA004 (a spouse left on a
# default that names no estate) is hard from birth, 2026-10-01: its 125 first
# findings — Глуповы Горы wives on «крестьянка» beside «крестьянин вотчины
# г-на Ноздрева» — were given their husband's estate in the same commit.
# status_orthography (SOR001) is hard from birth, 2026-10-01: a status= or
# departure_reason= in pre-reform spelling (the maintainers' ruling — names keep the
# scribe's spelling, classification fields are modern). Its 91 first findings
# (Маниловка 77, Глуповы Горы 13, Заманиловка 1) were rewritten in the same wave.
# status_redundancy (VSR001) is CSR001's rule for the three VITAL verbs and is
# HARD, not advisory: unlike the census corpus it reached 0 in the same commit
# that introduced it (five relative() fathers repeating their own village's
# status_male), so gating costs nothing and any new one is caught while
# authoring. Same reasoning already applied to marriage_residence above.
# relative_attachment (RLA001-RLA003) goes the other way — advisory, because
# none of its findings is a mechanical no-op the way VSR001's five were.
# RLA001 is the bulk (44): refs the translator never resolves into a
# relationship edge, 41 of them the unnumbered «восприемница» that the
# relationship_ref ALLOWLIST blesses but generator.py only ever matches as
# «восприемника №N». Rewriting those would emit ~41 new gprel_union resources —
# a real apply, not a lint fix. RLA002-RLA004 (7) each need a human reading of
# the scan: which of two contradictory readings is wrong, or whether the
# kinship itself is mis-modelled (a «приведенная дочь» wants STEP_FATHER).
# deaths_burial_date (DBD001/DBD002) is hard from birth, like VSR001: the eight
# burials-before-death `verso facts --check date-order` found were fixed (six) or
# declared `source_date_error=` (two), so it gates at zero and
# asks the same question while the record is being typed instead of after
# generation.
# reviewed_redundancy (RVR001) is advisory although its fix IS a mechanical
# no-op, because of WHEN it fires: a лист is released by adding
# `page(…, reviewed=True)` on top of entries already released one by one, so
# every finding appears in the middle of a sweep, in the file the author is
# still editing. Gating would fail CI on the commit that closes a лист and
# force the cleanup into that same commit; advisory lets the removal be its own
# reviewed edit.
# retractions (RET001-RET003) is hard from birth, like DBD001: 0 findings on
# the 937 DSL files when it landed (2026-09-25), and an age retraction that
# names no age is a slip, never a judgement call.
# witness_side splits by severity (2026-10-01). WSD001 (a side= anywhere but
# a marriage's witness1..6) and WSD002 (side= against the witness's own words)
# are hard: each is a slip, never a reading, and the corpus held 0 of either
# when `side=` was introduced. WSD003-WSD006 are advisory: a side written only
# in words (WSD003) is the whole Маниловка corpus until its migration, and a
# record half-declared (WSD004), a groom's surety after a bride's (WSD005) or
# more than three per side (WSD006) each want a look at the scan, not a fix.
# residence_title is hard: RTV001 (a Горюхино-parish landlord's or ясачный
# status against the village) and RTV002 (Глуповы Горы: an owner named in
# Горелово, a state peasant in the село) — 0 in the corpus. Its advisory half,
# RTV003 (a bare «крестьянин» of Горелово or the село before 1861), was retired
# on 2026-10-09: the books write plain «крестьянин», and the DSL keeps that.
# civil_register (ZGS001-ZGS002) is hard from birth: no book carried civil=True when it
# came, and a church slot in an act or a registration before the birth is a slip, never a
# reading. ZGS003-ZGS005 are advisory: each asks whether the book really writes it so.
# dsl_imports (IMP001) is hard from birth: the codemod left every DSL file on the
# facade, its catalogs and corpus.statuses, and a v0 import no longer loads.
LINTERS: tuple[Linter, ...] = (
    Linter("single_line_calls", _check_single_line_calls_structured, check_single_line_calls.check_file),
    Linter("genders", check_genders.check_file_structured, check_genders.check_file),
    Linter("names", check_names.check_file_structured, check_names.check_file),
    Linter("relationship_ref", check_relationship_ref.check_file_structured, check_relationship_ref.check_file),
    Linter("ages", check_ages.check_file_structured, check_ages.check_file),
    Linter("hidden_flag", check_hidden_flag.check_file_structured, check_hidden_flag.check_file),
    Linter("parent_member", check_parent_member.check_file_structured, check_parent_member.check_file),
    Linter("birth_redundancy", check_birth_redundancy.check_file_structured, check_birth_redundancy.check_file),
    Linter("deaths_residence", check_deaths_residence.check_file_structured, check_deaths_residence.check_file),
    Linter("deaths_relatives", check_deaths_relatives.check_file_structured, check_deaths_relatives.check_file),
    Linter("deaths_burial_date", check_deaths_burial_date.check_file_structured, check_deaths_burial_date.check_file),
    Linter("marriage_residence", check_marriage_residence.check_file_structured, check_marriage_residence.check_file),
    Linter("parent_status", check_parent_status.check_file_structured, check_parent_status.check_file),
    Linter("census_redundancy", check_census_redundancy.check_file_structured, check_census_redundancy.check_file, advisory=True),
    Linter("census_status_redundancy", check_census_status_redundancy.check_file_structured, check_census_status_redundancy.check_file, advisory=True),
    Linter("census_age", check_census_age.check_file_structured, check_census_age.check_file, advisory=True),
    Linter("census_member_lines", check_census_member_lines.check_file_structured, check_census_member_lines.check_file),
    Linter("census_parent_link", check_census_parent_link.check_file_structured, check_census_parent_link.check_file, advisory=True),
    Linter("residence_title", check_residence_title.check_file_structured, check_residence_title.check_file),
    Linter("unmapped_location", check_unmapped_location.check_file_structured, check_unmapped_location.check_file, advisory=True),
    Linter("external_sources", check_external_sources.check_file_structured, check_external_sources.check_file),
    Linter("name_lists", check_name_lists.check_file_structured, check_name_lists.check_file),
    Linter("patronymic_form", check_patronymic_form.check_file_structured, check_patronymic_form.check_file, advisory=True),
    Linter("name_gender_agreement", check_name_gender_agreement.check_file_structured, check_name_gender_agreement.check_file, advisory=True),
    Linter("marital_status", check_marital_status.check_file_structured, check_marital_status.check_file),
    Linter("status_redundancy", check_status_redundancy.check_file_structured, check_status_redundancy.check_file),
    Linter("status_orthography", check_status_orthography.check_file_structured, check_status_orthography.check_file),
    Linter("relative_attachment", check_relative_attachment.check_file_structured, check_relative_attachment.check_file, advisory=True),
    Linter("reviewed_redundancy", check_reviewed_redundancy.check_file_structured, check_reviewed_redundancy.check_file, advisory=True),
    Linter("retractions", check_retractions.check_file_structured, check_retractions.check_file),
    Linter("witness_side", check_witness_side.check_file_structured, check_witness_side.check_file),
    Linter("witness_side_advisory", check_witness_side.check_file_advisory_structured, check_witness_side.check_file_advisory, advisory=True),
    Linter("civil_register", check_civil_register.check_file_structured, check_civil_register.check_file),
    Linter("civil_register_advisory", check_civil_register.check_file_advisory_structured, check_civil_register.check_file_advisory, advisory=True),
    Linter("dsl_imports", check_dsl_imports.check_file_structured, check_dsl_imports.check_file),
)


def check_file_json(path: Path) -> list[dict[str, Any]]:
    """Run every registered linter on a file and return structured results.

    A crashed check reports itself as an error finding — it must never
    silently pass as "no issues". SyntaxError alone stays quiet here:
    single_line_calls already reports the file's SyntaxError once, and a
    half-typed IDE buffer must not produce one duplicate per linter.
    """
    results = []
    for linter in LINTERS:
        try:
            issues = linter.structured(path)
        except SyntaxError:
            issues = []
        except Exception as exc:
            issues = [as_dict(issue("LNT001", "crashed", 1, level="error", linter=linter.name,
                                    error=type(exc).__name__, detail=str(exc)))]
        results.append({
            "file": str(path),
            "linter": linter.name,
            "issues": [_printed(issue) for issue in issues],
        })
    return results


def _printed(issue: dict[str, Any]) -> dict[str, Any]:
    """A finding as `--json` prints it: its code, params and token — what its message is,
    in no language — right after the message, then the columns and the fix as the check wrote them."""
    out: dict[str, Any] = {}
    for key, value in issue.items():
        out[key] = value
        if key == "message":
            out.update(code=getattr(value, "code", ""), params=dict(getattr(value, "params", {})),
                       token=getattr(value, "token", None))
    return out


def _pop_option(args: list[str], flag: str) -> str | None:
    """Remove `--flag VALUE` from `args` and return VALUE (None if absent)."""
    if flag not in args:
        return None
    i = args.index(flag)
    if i + 1 >= len(args):
        raise SystemExit(f"{flag} needs a path")
    args.pop(i)          # the flag
    return args.pop(i)   # its value, now shifted into the flag's slot


def _village_files(paths: list[str]) -> list[str]:
    """`--villages`: every DSL file of every village of the workspace, in its order; paths beside it are refused."""
    if paths:
        raise SystemExit(str(t("linters.dsllint.villages_take_no_paths")))
    from verso.core import workspace
    from verso.core.pipeline.load import dsl_files
    ws = workspace.current()
    here = Path.cwd().resolve()
    # Named from the working directory where they lie under it, as a shell's glob names them: the
    # baseline's lines and the findings carry the path as given.
    return [str(path.relative_to(here) if path.is_relative_to(here) else path)
            for village in ws.villages for path in dsl_files(ws.village_dir(village).resolve())]


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} [--json] [--fix [--dry-run]] "
              f"[--baseline FILE [--update-baseline]] (--villages | <file.py> ...)", file=sys.stderr)
        return 1

    args = sys.argv[1:]
    json_mode = "--json" in args
    if json_mode:
        args.remove("--json")
    villages = "--villages" in args
    if villages:
        args.remove("--villages")
    # --fix rewrites instead of reporting. It is deliberately its own mode
    # rather than a flag on a lint run: a check that edits files while also
    # deciding an exit code is a check nobody trusts in CI.
    fix_mode = "--fix" in args
    if fix_mode:
        args.remove("--fix")
    dry_run = "--dry-run" in args
    if dry_run:
        args.remove("--dry-run")
    if fix_mode:
        from verso.ru.linters import fixes
        if villages:
            args = _village_files(args)
        results, code = fixes.run([Path(a) for a in args], dry_run=dry_run)
        print(fixes.format_report(results, dry_run=dry_run))
        return code
    if dry_run:
        raise SystemExit("--dry-run only means something with --fix")
    # The baseline gates ADVISORY findings only, and only when asked for: the
    # IDE (--json) must keep showing every finding, and a bare run stays the
    # print-and-exit-0 tool it has always been.
    update_baseline = "--update-baseline" in args
    if update_baseline:
        args.remove("--update-baseline")
    baseline_path = _pop_option(args, "--baseline")
    if update_baseline and baseline_path is None:
        raise SystemExit("--update-baseline needs --baseline FILE")
    if villages:
        args = _village_files(args)

    all_results = []
    all_errors = []
    all_warnings = []
    # What the baseline holds of each advisory finding — its text and its code and params.
    advisory: list[tuple[str, Any]] = []

    for arg in args:
        p = Path(arg)
        if not p.is_file():
            if json_mode:
                all_results.extend([
                    {"file": str(p), "linter": linter.name, "issues": []}
                    for linter in LINTERS
                ])
            continue

        if json_mode:
            all_results.extend(check_file_json(p))
        else:
            # Text mode runs the plain checks unwrapped: a crashed check
            # raises and fails the run loudly (traceback + non-zero exit).
            for linter in LINTERS:
                if linter.advisory and baseline_path is not None:
                    # One run, the structured one: it gates and it prints the new findings.
                    advisory.extend((f"{p}:{i['line']}: {i['message']}", i["message"])
                                    for i in linter.structured(p))
                elif linter.advisory:
                    all_warnings.extend(linter.plain(p))
                else:
                    all_errors.extend(linter.plain(p))

    if json_mode:
        print(json.dumps(all_results, ensure_ascii=False))
        return 0 if not all_errors else 1

    for e in all_errors:
        print(e, file=sys.stderr)

    if baseline_path is None:
        for w in all_warnings:
            print(f"warning: {w}", file=sys.stderr)
        return 0 if not all_errors else 1

    return _report_against_baseline(
        Path(baseline_path), advisory, bool(all_errors), update_baseline)


def _report_against_baseline(path: Path, warnings: list[tuple[str, Any]],
                             had_errors: bool, update: bool) -> int:
    """Gate advisory findings on the baseline (`verso.ru.linters.baseline`), each by its code and
    params."""
    from verso.ru.linters import baseline as bl

    findings = [bl.structured(f, code=getattr(message, "code", ""), params=dict(getattr(message, "params", {})),
                              printed=str(message))
                for line, message in warnings if (f := bl.parse_warning(line)) is not None]
    unparsed = len(warnings) - len(findings)

    if update:
        bl.write(path, findings)
        print(f"baseline rewritten with {len(findings)} advisory findings → {path}")
        return 0 if not had_errors else 1

    new, fixed = bl.classify(findings, bl.load(path))
    if fixed:
        print(f"{fixed} baselined advisory finding{'' if fixed == 1 else 's'} "
              f"no longer occur{'s' if fixed == 1 else ''} — re-run with "
              f"--update-baseline to shrink the baseline.")
    if unparsed:
        # Never let an unrecognised warning shape slip through unseen: it would
        # be permanently un-baselineable and therefore permanently invisible.
        print(f"warning: {unparsed} advisory finding(s) had an unparseable "
              f"shape and are not gated", file=sys.stderr)
    if not new:
        print(f"no new advisory DSL findings ({len(findings)} baselined).")
        return 0 if not had_errors else 1

    print(f"\nNEW advisory DSL findings ({len(new)} new, "
          f"{len(findings) - len(new)} baselined):\n", file=sys.stderr)
    for f in new:
        print(f"  {f.line_text()}", file=sys.stderr)
    print("\nThese checks are advisory because the corpus cannot reach zero on "
          "them today,\nbut the existing debt is baselined — so anything above "
          "it is newly introduced.\nFix it, or record it deliberately with "
          "--update-baseline.", file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
