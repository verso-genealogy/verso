# The review ratchet

**English** · [Русский](review-ratchet.ru.md)

One flag says whether a record has been read against its scan, and a list says which unread
records are already on Geni (`verso.ru.dsl.records.reviewed`, `verso.core.ratchet`).

## `reviewed=`

`reviewed=False` holds a record off Geni and out of the facts layer, on every record type. It is
resolved innermost-first — the record, its `page(…)`, its record set (`birth_records(…,
reviewed=…)`, `census_records(…)`, …) — and defaults to `True`. Where the flag is written decides
how it is dropped:

- on the record (`birth(…, reviewed=False)`) — dropping it makes the record visible and mints its
  profiles;
- on a page (`page("341об", reviewed=False, …)`) — reviewing one record of the leaf writes an
  explicit `reviewed=True` on it, and the last one removes the page's flag and every explicit
  `True` with it;
- on the record set — dropped the same way, record by record.

RVR001 flags a `reviewed=` restating the value it would inherit.

## The list

A corpus can hold records that reached Geni before they were read. Each village's
`unreviewed_on_geni.tsv` lists them by fingerprint; an unreviewed record reaches Geni only while the
list names it unchanged, and a new one is held.

- **The fingerprint** is the AST of the record's call without `reviewed=`, of every call around it
  without its records or flag, and of the file's module-level assignments (`DEFAULTS`): formatting
  and comments do not count; a changed name, number, date, лист or default does; a change of the
  translator does not.
- **A listed record edited without being reviewed is held** — its profiles would leave the tree and
  the next plan destroy them — so `verso review-ratchet --village V` fails («changed»). Review it, or revert
  the edit.
- **Or rebind it**: `verso review-ratchet --village V --rebind FILE` repoints each «changed» line of the file at
  the held record with its own call, number, sex and лист, one line to one record, and refuses
  anything else.
- **The list only shrinks.** A line whose record is reviewed is struck (`--prune`); a CI check with
  `--base REV` fails a line the base commit's list lacks. `--seed` writes a village's list once,
  from Terraform state.
