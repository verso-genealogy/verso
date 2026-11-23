# AGENTS.md — the toy corpus

A sample of the project map the reading skills of `verso-reading` look for: what a corpus tells an agent
before it reads a scan. Everything here is invented, like the village.

## The corpus

One village, Степанчиково, with a church of its own; its landlord Егор Ильич Ростанев. The books
are under `Степанчиково/<year>/`, one DSL file per book and year.

## Where the frames are

A дело's frames go into a directory of its own outside this tree, named by folio (`<кадр>_<лист>[об]`).
This toy has no scans; a real corpus says here where each archive's frames come from and where the record of
each дело is kept — its first and last лист, its parts, inserted leaves.

## The rules

- **Writing a record**: the library's rules of a record (the verso repository's guide «The rules of a
  record»): names as written, a patronymic the entry does not write is `None`, kinship another record tells
  goes into `comment=`, doubt into `comment=`, `reviewed=False` on everything read from a scan.
- **Statuses**: the landlord's peasants take the constants of `corpus/statuses.py`
  (`from corpus.statuses import ROSTANEV_EI_PEASANT_MALE`); anyone else, the catalog `verso.ru.dsl.statuses`.
- **Places**: a residence is a key of `corpus/places.toml` — Степанчиково, Капустино.

## Regional notes

The surnames of the village: Видоплясов, Фалалеев, Ежевикин. A household is often written with a
patronymic and no surname; read the year on the bare patronymics too.

## After reading a year

```sh
verso dsllint Степанчиково/<year>/*.py                       # no finding of level error
verso export-csv --village Степанчиково --year <year>        # exits 0: every file builds
verso facts --village Степанчиково --check name-days         # and wedding-calendar, baptism-lag, burial-lag, wedding-ages
verso death-age --village Степанчиково
verso sibling-spacing --village Степанчиково
verso stale-claims --village Степанчиково
```

The checks but `stale-claims` read reviewed records: ask them again once a year is read back against the scan.
