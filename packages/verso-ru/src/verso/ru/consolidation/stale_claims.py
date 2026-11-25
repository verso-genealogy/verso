#!/usr/bin/env python3
"""Flag a comment that calls a record the earliest one, when an earlier record
of the same person is now in the corpus.

**Why it exists.** The sweep reads backwards, so "самая ранняя запись",
"старший известный ребёнок" and "первое упоминание" are claims with a shelf
life measured in one year. Reading Глуповы Горы 1893 falsified three
statements committed with 1894 the same morning; 1894 had falsified two written
with 1895. This is not carelessness — a superlative about a corpus that grows
downwards is *expected* to rot — but it rots silently, and the corpus is where
the conclusions live.

The check does not try to understand what is claimed. It looks for the
formulaic superlatives and asks a mechanical question: **is this record still
the earliest one naming its own subject?** If an earlier record names the same
father, deceased or groom, the superlative is at least suspect and a human
should look. Godparents and witnesses are deliberately NOT subjects — a comment
routinely says "самое раннее упоминание" about a godparent while the record's
own family is attested earlier, and treating those as subjects would bury the
real findings.

Advisory triage, like `estate-conflicts` and `union-dups`: a finding is a
prompt to re-read two records, not a verdict. Read-only and network-free.

Identity folds first-name variants through `names.csv` («Имя-основа»), so
«Алексѣй Ѳедоровъ» of one year and «Алексій» of another are one man — see
`person_key` and `verso.ru.naming.matching_base`. Until 2026-09-05 they were two,
and the check under-reported: it named the earliest record it could SEE rather
than the earliest there is.

Run:
    python3 -m verso.ru.consolidation.stale_claims --village "Глуповы Горы"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from verso.core.i18n import Message
from verso.ru.consolidation.death_age import PersonKey, as_date, person_key
from verso.ru.messages import t

# The formulaic register these comments are written in. Kept deliberately short:
# every pattern here has to be a phrase that ASSERTS PRIMACY, not one that merely
# mentions a date.
CLAIM_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"сам\w* ранн\w+", "самая ранняя"),  # i18n: content — the primacy phrases the notes write
    # The word «первый» in its own endings, not any word that starts with «перв»: «первоначальная
    # запись» is the act as first written, before a correction, and claims nothing about order.
    (r"\bперв(?:ая|ое|ой|ую|ый|ым|ые|ых|ыми|ого|ому|ыя) (?:метрическ\w+ )?(?:запись|упоминание)",  # i18n: content — the primacy phrases the notes write
     "первая запись"),  # i18n: content — the primacy phrases the notes write
    (r"старш\w+ (?:известн\w+ )?(?:ребёнок|ребенок|сын|дочь)", "старший ребёнок"),  # i18n: content — the primacy phrases the notes write
    (r"прежн\w+ сам\w+ ранн\w+", "прежняя самая ранняя"),  # i18n: content — the primacy phrases the notes write
)

# «Отодвигается с 1897 на 1894 год» is NOT here on purpose: it records what a
# record did when it was read, which stays true no matter what turns up below
# it. Only a claim of PRIMACY can be falsified by a deeper year.

# A comment that already carries a dated retraction has been dealt with — the
# reader is being told the claim is dead, which is the outcome this check wants.
# Same contract as `source_date_error` for `verso date-order`: declare it and the
# check stands down.
RETRACTED = re.compile(
    r"(?:снят\w*|исправлен\w*|отменён\w*|отменен\w*|больше не (?:держит|самая)|"  # i18n: content — the retraction the notes write
    r"лишь до|только до)\s*\(?\d{2}\.\d{2}\.\d{4}|"  # i18n: content — the retraction the notes write
    r"(?:считалась|была|держал\w*)\s+(?:лишь|только)\s+до\s+\d{2}\.\d{2}\.\d{4}",  # i18n: content — the retraction the notes write
    re.IGNORECASE)

# A superlative scoped to the whole corpus is the one that breaks loudest and
# is quoted in README and the family file, so it is ranked above a claim about
# one person's own record.
# «Корпусу неизвестен» is the commonest phrase in these comments and says
# nothing about scope, so the word only counts when it stands beside the
# superlative itself.
CORPUS_SCOPE = re.compile(r"корпус", re.IGNORECASE)  # i18n: content — the notes' word for the corpus
CORPUS_WINDOW = 70

_COMPILED = tuple((re.compile(p, re.IGNORECASE), label) for p, label in CLAIM_PATTERNS)


def _kind_name(kind: str) -> Message:
    """A record kind the check reads, as the report names it in the interface's language."""
    if kind == "рождение":  # i18n: content — a record kind, internal
        return t("consolidation.stale_claims.kind.birth")
    if kind == "брак":  # i18n: content — a record kind, internal
        return t("consolidation.stale_claims.kind.marriage")
    return t("consolidation.stale_claims.kind.death")


@dataclass(frozen=True)
class RecordRef:
    kind: str
    year: int
    record_num: str
    source: str
    when: date

    def __str__(self) -> str:
        return f"{_kind_name(self.kind)} {self.year} № {self.record_num} [{self.source}]"


@dataclass(frozen=True)
class StaleClaim:
    scope: str            # CORPUS | PERSON
    phrase: str
    subject: str
    record: RecordRef
    earlier: RecordRef
    excerpt: str


def same_person(candidate: PersonKey, subject: PersonKey) -> bool:
    """Stricter than `PersonKey.matches`, and it has to be.

    `matches` treats a missing patronymic as compatible, which is right when
    pairing ONE person across two slots — a child carries no patronymic. Here it
    is wrong: the question is whether an EARLIER record names the same adult,
    and a newborn «Иоаннъ» would satisfy the tolerant rule against his own
    father «Иоаннъ Михайловъ». So both patronymics must be present and equal,
    and surnames must agree wherever both are written.
    """
    if candidate.name != subject.name:
        return False
    if not candidate.patronymic or not subject.patronymic:
        return False
    if candidate.patronymic != subject.patronymic:
        return False
    if candidate.surname and subject.surname and candidate.surname != subject.surname:
        return False
    return True


def _display(key: PersonKey) -> str:
    return " ".join(bit for bit in (key.display, key.patronymic, key.surname) if bit).title()


def _subjects(rec, kind: str) -> list[PersonKey]:
    """The people a record is ABOUT — never its godparents or witnesses."""
    if kind == "рождение":  # i18n: content — a record kind, internal
        slots = ("father", "mother")
    elif kind == "смерть":  # i18n: content — a record kind, internal
        slots = ("deceased",)
    else:
        slots = ("groom", "bride")
    keys = [person_key(getattr(rec, s, None)) for s in slots]
    if kind == "смерть":  # i18n: content — a record kind, internal
        for rel in getattr(rec, "relatives", None) or []:
            keys.append(person_key(rel.person))
    return [k for k in keys if k is not None]


def _record_date(rec, kind: str, fallback_year: int) -> date | None:
    year = getattr(rec, "year", None) or fallback_year
    if kind == "рождение":  # i18n: content — a record kind, internal
        return as_date(year, getattr(rec, "b_month", None), getattr(rec, "b_day", None))
    if kind == "смерть":  # i18n: content — a record kind, internal
        return as_date(year, getattr(rec, "d_month", None), getattr(rec, "d_day", None))
    return as_date(year, getattr(rec, "w_month", None), getattr(rec, "w_day", None))


def _everyone(rec) -> list[PersonKey]:
    """Every person a record names, in any slot — the index of attestations."""
    slots = ("child", "father", "mother", "deceased", "groom", "bride",
             "god_parent1", "god_parent2", "god_parent3", "god_parent4",
             "witness1", "witness2", "witness3", "witness4", "witness5", "witness6")
    keys = [person_key(getattr(rec, s, None)) for s in slots]
    for rel in getattr(rec, "relatives", None) or []:
        keys.append(person_key(rel.person))
    return [k for k in keys if k is not None]


def matched_phrases(comment: str | None) -> list[str]:
    if not comment:
        return []
    return [label for pattern, label in _COMPILED if pattern.search(comment)]


def _excerpt(comment: str, phrase_re: re.Pattern[str], width: int = 90) -> str:
    m = phrase_re.search(comment)
    if not m:
        return comment[:width]
    start = max(0, m.start() - width // 3)
    return ("…" if start else "") + comment[start:start + width].strip() + "…"


def find_stale_claims(record_sets: list[tuple[object, str, str]]) -> list[StaleClaim]:
    """record_sets: (records object, kind, source) for births/marriages/deaths."""
    entries: list[tuple[RecordRef, object, str, list[PersonKey]]] = []
    attestations: dict[PersonKey, list[RecordRef]] = {}

    for records, kind, source in record_sets:
        for rec in getattr(records, "records", []):
            year = getattr(rec, "year", None) or getattr(records, "year", 0)
            when = _record_date(rec, kind, getattr(records, "year", 0))
            if when is None:
                continue
            ref = RecordRef(kind=kind, year=year,
                            record_num=str(getattr(rec, "record_num", "") or "?"),
                            source=source, when=when)
            for key in _everyone(rec):
                attestations.setdefault(key, []).append(ref)
            entries.append((ref, rec, kind, _subjects(rec, kind)))

    findings: list[StaleClaim] = []
    for ref, rec, _kind, subjects in entries:
        comment = getattr(rec, "comment", None)
        phrases = matched_phrases(comment)
        if not phrases or not comment or RETRACTED.search(comment):
            continue
        for subject in subjects:
            earlier = [r for key, refs in attestations.items() if same_person(key, subject)
                       for r in refs if r.when < ref.when]
            if not earlier:
                continue
            first = min(earlier, key=lambda r: r.when)
            pattern = next(p for p, label in _COMPILED if label == phrases[0])
            hit = pattern.search(comment)
            near = comment[max(0, hit.start() - CORPUS_WINDOW):
                           hit.end() + CORPUS_WINDOW] if hit else ""
            scope = "CORPUS" if CORPUS_SCOPE.search(near) else "PERSON"
            findings.append(StaleClaim(
                scope=scope, phrase=phrases[0], subject=_display(subject),
                record=ref, earlier=first, excerpt=_excerpt(comment, pattern)))
            break   # one finding per record: the reader re-reads it once
    findings.sort(key=lambda f: (f.scope != "CORPUS", f.record.year, f.record.record_num))
    return findings


def format_report(findings: list[StaleClaim]) -> str:
    if not findings:
        return "claim-check: OK — 0 findings (no primacy claim is contradicted)."
    corpus = sum(1 for f in findings if f.scope == "CORPUS")
    lines = [f"claim-check: {len(findings)} finding(s) — {corpus} CORPUS-scoped, "
             f"{len(findings) - corpus} about one person\n"]
    for f in findings:
        lines.append(f"[{f.scope}] {f.record}  «{f.phrase}»")
        lines.append(str(t("consolidation.stale_claims.subject", subject=f.subject)))
        lines.append(str(t("consolidation.stale_claims.earlier", earlier=f.earlier, when=f.earlier.when.isoformat())))
        lines.append(f"    {f.excerpt}\n")
    lines.append(str(t("consolidation.stale_claims.perishable")))
    lines.append(str(t("consolidation.stale_claims.signal")))
    return "\n".join(lines)


def findings_to_json(findings: list[StaleClaim]) -> str:
    return json.dumps([
        {"scope": f.scope, "phrase": f.phrase, "subject": f.subject,
         "record": str(f.record), "record_date": f.record.when.isoformat(),
         "earlier": str(f.earlier), "earlier_date": f.earlier.when.isoformat(),
         "excerpt": f.excerpt}
        for f in findings], ensure_ascii=False, indent=2)


def load_all_records(village_dir: Path) -> list[tuple[object, str, str]]:
    from verso.core.pipeline.load import load_module
    from verso.ru.dsl.kinds import SOURCE_PATTERNS
    from verso.ru.dsl.records.births import BirthRecords
    from verso.ru.dsl.records.deaths import DeathRecords
    from verso.ru.dsl.records.marriages import MarriageRecords
    from verso.core.records.sets import record_sets

    wanted =((SOURCE_PATTERNS[0], BirthRecords, "рождение"),  # i18n: content — a record kind, internal
              (SOURCE_PATTERNS[1], MarriageRecords, "брак"),  # i18n: content — a record kind, internal
              (SOURCE_PATTERNS[2], DeathRecords, "смерть"))  # i18n: content — a record kind, internal
    found: list[tuple[object, str, str]] = []
    for pattern, expected, kind in wanted:
        for path in sorted(village_dir.glob(pattern)):
            try:
                mod, name = load_module(path), path.stem
            except Exception as exc:
                print(f"WARNING: failed to load {path}: {exc}", file=sys.stderr)
                continue
            source = str(path.relative_to(village_dir))
            obj = getattr(mod, name, None)
            if isinstance(obj, expected):
                found.append((obj, kind, source))
                continue
            for value in record_sets(vars(mod), expected).values():
                found.append((value, kind, source))
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Flag a primacy claim («самая ранняя запись», «старший "  # i18n: content — the phrases it looks for, quoted
                    "ребёнок») that a later-found record contradicts.")  # i18n: content — the phrases it looks for, quoted
    ap.add_argument("--village", default=".", help="village dir (default: cwd)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--corpus-only", action="store_true",
                    help="only claims scoped to the whole corpus — the loudest ones")
    args = ap.parse_args(argv)

    findings = find_stale_claims(load_all_records(Path(args.village)))
    if args.corpus_only:
        findings = [f for f in findings if f.scope == "CORPUS"]
    print(findings_to_json(findings) if args.json else format_report(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
