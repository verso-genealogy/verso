# The toy example

**English** · [Русский](README.ru.md)

`toy/` is a whole workspace of its own: one invented village, «Степанчиково» — after Dostoevsky's
«Село Степанчиково и его обитатели» — its landlord Егор Ильич Ростанев, a few of his peasants, and
four books: births, marriages and deaths of 1850 and one двор of the 1858 revision. The people,
the days and the shelfmarks are made up.

```
toy/
  AGENTS.md                     # the project map the reading skills look for: the rules, the checks
  verso.toml                    # the workspace: the village, the names lexicon (schema 6), the corpus's data
  names/                        # the workspace's names layer over the base verso-ru ships: names.tsv,
                                #   forms.tsv, patronymics.tsv — empty here, the base knows every
                                #   name of the village; `verso names add` writes into it
  corpus/                       # places, the landlord (estates.toml), an event, his statuses
  Степанчиково/
    village.toml                # the Geni project its profiles join
    1850/stepanchikovo_{births,marriages,deaths}_1850.py
    1858/stepanchikovo_census_1858.py
    terraform/geni/main.tf      # the module's frame; generate-tf writes the rest
```

The base answers with pre-reform church forms (e.g. Иван → Иоанн in the old-spelling fields and resource ids); a row of the example's own layer (`names/`) overrides that.

`python examples/run.py` copies `toy/` to a temporary directory and runs `verso` over the copy,
step by step:

1. `verso workspace villages` — the workspace is found;
2. `verso dsllint --json …` — no finding of level error;
3. `verso export-csv --village Степанчиково` — a CSV per book;
4. `verso export-records --village Степанчиково` — the records JSON;
5. `verso records-schema --validate records` — valid against the schema;
6. `verso generate-tf --village Степанчиково` — Geni's Terraform;
7. `verso facts --village Степанчиково` — the facts layer;
8. `verso svyatcy near 1850-04-16 --gender M` — the святцы around a day.

`--keep DIR` leaves the copy in DIR to look at; `--workspace DIR` runs over a workspace of your
own. It needs the library installed with its extras (see the [README](../README.md)):

```
pip install "verso-core[schema]" "verso-ru[xlsx,dsl-tools]"
```
