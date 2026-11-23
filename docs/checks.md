# The checks

**English** · [Русский](checks.ru.md)

The linters read a file; the checks read the records — a village's, built — and find what they
contradict: a name no saint near the birth supports, a wedding in a fast, a burial age the birth record
disproves. Each finding is a reason to read the scan again, never a correction to apply: «так в
подлиннике» is an answer too, and the record says so ([the rules of a record](writing-records.md)). The
numbers each check holds are in [the reference](reference/checks.md).

## Before any check

- **Every file loads.** A file that does not import is skipped with a warning, and the checks report on
  what is left. `verso export-csv --village V` exits 1 on such a file; `verso dsllint` does not see it.
- **The checks read reviewed records.** A record that is `reviewed=False` is read only by
  `verso stale-claims`, and by the signals of one record (`signals_on_json`, [records JSON](records-json.md)).
  A year just read answers the rest once it is reviewed.
- **The dates are Julian** until February 1918, as the books wrote them; the святцы and the paschalion are
  of that calendar.
- **Exit codes**: 1 on a finding, 0 on none (`verso facts`: 2 when the village is not found). A finding a record's note
  stands down (`calendar_note=`, `lag_note=`, `age_note=`) is counted apart and is not a finding.

## One record

Six checks need one record and nothing else, so they speak on a fresh workspace, before anything is
consolidated. `verso facts --village V --check CHECK` asks one of them of the village.

| Check | It asks | Answered by |
|---|---|---|
| `name-days` | a newborn's name no saint of the 1906 Требник supports near the birth: a window from three days before the birth to three past the later of the christening and the eighth day; a finding lies more than 30 days outside | `calendar_note=` |
| `wedding-calendar` | a wedding in a fast, сырная or Светлая седмица, Святки, on 29 August or 14 September (HIGH); on a Tuesday, Thursday, Saturday, the eve of a feast, Meatfare Sunday (LOW) — the movable days by the paschalion, up to 1917 | `calendar_note=` |
| `baptism-lag` | a christening more than 11 days after the birth; HIGH when its day is smaller than the birth's, so its month was taken as the next one and one of the two days is probably misread | `lag_note=` |
| `burial-lag` | a burial more than 3 days after the death; HIGH past 9 | `lag_note=` |
| `wedding-ages` | an age at the wedding more than half a year under the minimum of its date (15 and 13 from the decree of 17 December 1774, 18 and 16 from that of 19 July 1830; nothing before); spouses more than 20 years apart (LOW) | `age_note=` |
| `date-order` | of one entry: a christening before the birth, a burial before the death | `source_date_error=` |

The lags, the ages and the parents' checks below come from Gramps' Verify tool (BaptTooLate, BuryTooLate,
EarlyMarriage, LargeAgeGapFamily, DeadParent, LargeChildrenSpan), with thresholds measured on a corpus of
the books rather than taken from it. On the toy example's births (`examples/`):

```text
$ verso facts --village Степанчиково --check name-days
name-days: 1 of 2 births — the name's saint more than 30 days from the window (HIGH 0, LOW 1)
LOW — The window: birth −3 … max(christening, 8th day) +3 days. Most often the name was simply given out of the calendar.
If the source says so, write calendar_note="…" in the record.

[LOW] Прасковья: the nearest saint of the name is kept on 26.07, 93 days outside the window (born 14.04.1850, christened 16.04.1850).
    stepanchikovo_births_1850.py №1
```

When the ink fits two names, `verso svyatcy near 1850-04-16 --gender F --like Мария` lists the names kept
around that day, most like the reading first; `verso svyatcy dates Агапия --gender F` says when a name is
kept.

## Across records, before consolidation

These compare the records of a village by the names they write, so they too speak on a fresh workspace:

- `verso death-age` — a burial's age against the birth record of the same child (by the name and the
  parents): an age read in the wrong unit shows as a gap of twelve times;
- `verso sibling-spacing` — two children of one couple born less than 270 days apart: a birth year
  derived from a burial age in the wrong unit lands next to a recorded sibling;
- `verso stale-claims` — a comment calling a record the earliest («самая ранняя запись», «первое
  упоминание») when an earlier one of the same person is now in the corpus; it reads drafts too;
- `verso facts --check father-claims`, its class «inside one record» — a patronymic that does not come
  from the father the same entry names.

`--json` gives `death-age`, `sibling-spacing` and `stale-claims` to a tool.

## Across records, after consolidation

A corpus joins the records of one person into one profile — its consolidation. These ask the joined
people, and find nothing until there is any:

- `verso facts --check birth-claims` — two births of one person too far apart for one life;
- `verso facts --check father-claims`, «between records» — two fathers;
- `verso facts --check death-claims` — two deaths or two burials;
- `verso facts --check posthumous-birth` — a child after the mother's death, or more than 294 days after
  the father's;
- `verso facts --check children-span` — a mother's children more than 28 years apart;
- `verso facts --check date-order`, «between records» — an event of one record before an earlier one of
  another;
- `verso date-order` — the same question of the tree Geni shows, one birth per profile;
- `verso age-conflicts` — a parent too young or too old at a child's birth;
- `verso estate-conflicts` — one profile's records in two estates.

They look for a fold that went too far. The channels that look for one not yet made — `verso candidates`,
`verso union-duplicates`, `verso name-variants`, `verso split-couples`, `verso reconcile` — propose people
to join. All of them read and change nothing; a candidate is read on both records before anything is
folded.

## Names in the reports

A report's first word is not always its command's name:

| Command | The report says |
|---|---|
| `verso date-order` | `date-conflicts:` |
| `verso death-age` | `death-age-check:` |
| `verso stale-claims` | `claim-check:` |
| `verso union-duplicates` | `union-dups:` |

`verso date-order` asks the tree; `verso facts --check date-order` asks the records, each claim apart.

## In a corpus's CI

- `verso dsllint --baseline FILE` — advisory findings held by a ratchet ([linters](reference/linters.md));
- `verso stale --village V` — the generated Terraform and CSVs are what the DSL writes now;
- `verso facts-snapshot --village V --check` — `<village>/facts_findings.tsv` holds each check's count of
  findings; a count that moves is accepted in the commit that moved it (`verso facts-snapshot --village V`
  writes it);
- `verso records-schema --validate DIR` — the records JSON against its schema;
- `verso review-ratchet --village V` — the list of unreviewed records already on Geni
  ([the review ratchet](review-ratchet.md)).
