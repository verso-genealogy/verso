"""The Church's calendar, as the books were kept in it — a LEAF package.

Three questions the records can be asked against something they did not
write themselves:

* `julian` — day arithmetic in the Julian calendar (Julian Day Numbers).
* `paschalion` — the date of Pascha and the days on which венчание was not
  performed.
* `svyatcy` — which saints a given name commemorates, and on which days.

Stdlib and `verso.ru.naming` only, for the reason `verso.ru.census_revisions` gives:
the IDE plugins run the DSL linters with a bare `python3`, and a linter may
one day want to warn about a wedding in Lent while the date is typed.
"""
