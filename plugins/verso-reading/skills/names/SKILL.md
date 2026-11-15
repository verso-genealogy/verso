---
name: names
description: Reference for the names lexicon — the base verso-ru ships and the layers a corpus adds over it (names.tsv, forms.tsv, patronymics.tsv). Use when working with Russian historical names, patronymics, or resolving name validation lint errors.
---

Work with the names lexicon of the historical Russian genealogy records.

What a name is — its base, its forms, the patronymics it gives — is the **sum of layers**: the
base the library ships (`ru`, built from the 1906 Требник's alphabet, Wikidata and the metric
books' spellings) and, above it, the corpus's own layer or layers. The workspace's `verso.toml`
says which (schema 6 and later):

```toml
schema = 6
[names]
base = "ru"
layers = ["names"]        # the corpus's layer(s), directories relative to verso.toml
writable = "names"        # the one `verso names add` writes
```

The library's workspace guide, «The names lexicon», is the format in full (the markers,
`layer-diff`). This skill is how a corpus uses it. Where the corpus keeps its layer, and any check
of its own over it, the AGENTS.md проекта says.

## Quick recipe — `Unrecognized first name 'X'`

1. Ask the lexicon, not a file:

   ```bash
   verso names explain Зюзей                # every naming function's answer, and which layer gave it
   python -c "from verso.ru.naming import validate_first_name as v, matching_base as m; print(v('Зюзей'), m('Зюзей'))"
   ```

   The base ships inside verso-ru; most names are there, and the corpus layer holds only what the
   corpus answers otherwise.
2. A name neither holds → add it to the writable layer — see «Adding a name». A layer's rows are
   kept **sorted by key**; `verso names add` puts the row at its place.
3. Re-run the linter on the file (`verso dsllint <file>`) and `verso names check`; if the
   project holds its layer to recorded answers (an oracle of the questions its producers ask), run
   that check too.

## The three tables of a layer

Each is a TSV with a header row, one row per key, **sorted by key**. The order carries nothing:
an entry of an upper layer replaces the lower layer's entry of its key **whole**, and no row
«wins» by standing first.

| File | Key | Columns |
|---|---|---|
| `names.tsv` | `sex`, `name` | `bases` (the base form(s), `\|`-joined; empty = the name is its own base), `canonical`, `source`, `note` |
| `forms.tsv` | `sex`, `name` | `genitive`, `patronymic_m`, `patronymic_f`, `old_patronymic_m`, `old_patronymic_f`, `source` |
| `patronymics.tsv` | `sex`, `form` | `father`, `modern`, `old`, `source` — a pin: a short form read back to its father and modern form, or (`old`) a modern form's short one |

- `sex` is `M`, `F` or empty (a name of no sex; a patronymic tied to nothing). A forms row and a
  patronymic tied to a father always have a sex.
- **An empty forms cell is the rule's** (`verso.ru.naming.forms`): the layer derives the
  genitive, and a man's name its patronymics. Write a cell only where the corpus's answer is
  not the rule's.
- **`-` in a forms cell — «no such form»**: the rules do not fill it in, and no reverse lookup
  (a short patronymic → its father) finds a form there.
- **`-` in `bases` of a names row — removal**: that (sex, name) does not exist in this stack;
  the lower layers' entry of that key goes, with its forms. Use it where the base holds a name
  the corpus never writes for that sex (a saint's name of the other sex, say).
- **`source`**: `legacy` — carried over from old tables by `verso names layer-diff`;
  `ignore` — a name the lexicon knows and **leaves out on purpose** (validation passes, gender
  comes from the row's sex). A patronymic row with no father, modern or old is an ignored form.

## How a corpus layer is made from old tables

`verso names layer-diff --from-legacy DIR --base ru --oracle ORACLE.tsv --out LAYER` writes the
smallest layer over the base that answers every question of a names oracle (the questions the
corpus's producers asked, recorded once) as the old tables did. Keep the owner's ignore lists
whole on top of it.

Some rows keep an old answer that grammar or the святцы call wrong (an old row that won by its
place in the old table, e.g. Сергий → old patronymic «Сергеев» where the base says «Сергиев»).
They stay, deliberately, while the switch is meant to move no byte of output. They are corrected,
if the owner agrees, in a separate step that moves the output on purpose.

## Adding a name

`verso names add --gender М|Ж --name NAME [--base BASE] [--genitive …] [--patr-m …] [--source …]`
writes the row (and a forms row where forms are given) into the writable layer, refusing a row
the layers' linter finds hard (LEX001, LEX003, LEX007). By hand, the rows are:

- A **variant spelling**: `M<TAB>Зюзей<TAB>Пантелеимон<TAB><TAB>Маниловка МК 1850<TAB>` —
  `bases` the canonical form, which the sum must hold (LEX003).
- A **canonical name** the base lacks: `bases` empty.
- Its forms only where the rule is wrong for it (`forms.tsv`, the cells left empty that the
  rule gives right — LEX005 flags a cell equal to the rule's).
- A **one-off or non-name** («Имена», a title written as a name): a names row with source
  `ignore` — with a sex when the person's is known, and a `forms.tsv` row of `-` cells if the
  name must give no patronymic.
- An unknown **short patronymic** (`Unknown patronymic 'Карнелов'`): give its father a forms
  cell, or add a pin to `patronymics.tsv` (`M<TAB>Карнелов<TAB>Корнилий<TAB>Корнилиевич<TAB><TAB>…`),
  or, for a dubious form, an ignored row (form and source only).

Insert a hand-written row at its sorted place. Then `verso names check`. `verso names remove`
takes a row out again (a name only the base holds gets a removal row).

⚠ A changed answer can rename a res_name or rewrite a `geni_document.text` of a village already
on Geni (a canonical name, a patronymic). Compare the corpus's whole output before and after a
change to an existing row's answer, never only the linter.

## Checking the layer

```bash
verso names check            # the writable layer; --layer DIR one layer; --all every layer and the sum
```

| Code | Means | Gates |
|---|---|---|
| LEX001 | a key the lexicon cannot be asked by (not one Cyrillic word, a stress mark, a space, a bad sex) | yes |
| LEX002 | a key written twice in one table | yes |
| LEX003 | a base no layer of the sum holds | yes |
| LEX004 | a base that is itself a variant (a chain above the base) | **no** |
| LEX005 | a row that answers as the sum without it does (redundant) | no |
| LEX007 | two names give one short or modern patronymic, no pin settles it | yes |

LEX006 is the base's alone. **LEX004 is advisory on purpose**: `matching_base` takes one step, so
`Саламанида → Салманида → Соломонида` stops short — but repairing it changes `matching_base`,
which feeds res_names: a migration, not a cleanup.

## Python API — `verso.ru.naming`

Every function reads the summed lexicon:

```python
from verso.ru.naming import (
    validate_first_name, validate_old_patronymic, get_gender_from_name,
    get_gender_from_old_patronymic, canonicalize_name, canonicalize_patronymic,
    find_old_patronymic_by_modern, derive_patronymic, derive_old_patronymic,
    modernize_orthography, feminize_surname, degenitivize_surname, degenitivize_patronymic,
    name_from_genitive, matching_base,
)
```

- `validate_first_name(name)` — the lexicon holds it (any layer), or ignores it; always True for
  `None`, `''`, `'?'`, `'[имя]'`.
- `validate_old_patronymic(p, accept_full=False)` — a short form some name gives or a pin holds,
  or an ignored one; `accept_full=True` also takes a full «-ович/-евич» form whose father is known.
- `canonicalize_name(name, gender=None)` — the name's canonical form; `matching_base(name,
  gender)` — its base, one step (the identity checks fold names by it; never written anywhere).
- `canonicalize_patronymic(p)` — short → modern; raises `ValueError` when nothing gives `p`.
- `find_old_patronymic_by_modern(m)`, `father_name_for_patronymic(p)` — the reverse lookups.
- `derive_patronymic(father, gender)` / `derive_old_patronymic(father, gender)` — the father's
  forms cell, else the rule.

## Fixing lint errors

```bash
verso dsllint <village>/<year>/*.py
python -m verso.ru.linters.checks.names <village>/<year>/*.py   # the names check alone
```

**A finding on a name you just read from a scan is first a question about the reading.** Re-read the
crop at 4–5×. Add a row only when the scan plainly shows that form. Otherwise write the reading with
«?» after it and leave the lexicon alone: a row added to clear a finding on a misreading hides the
misreading. A reading agent once read «Ѳалѣевъ» for a plainer patronymic and added «Фалеев» to the lexicon.

| Finding | Fix |
|---|---|
| `Unknown first name 'X'`, a real name | a names row in the writable layer (a variant: its base) |
| …, an obscure one-off or a non-name | a names row with source `ignore` |
| `Unknown patronymic 'Y'` | the father's forms cell, a pin in `patronymics.tsv`, or an ignored form |
| `Unknown first name 'A B'` | split the name and the patronymic in `person()` |

### `PAF001` — full patronymic on a low-rank person (advisory)

`verso.ru.linters.checks.patronymic_form` warns when a full «-ович/-евич/-овна» patronymic
appears on a person whose status is not high-rank: pre-reform sources normally used the
short полуотчество (`Иванов`) for peasants. It is **advisory** (never fails CI). If the
source genuinely wrote the full form (WWI casualty cards, noble records), keep it
verbatim. Silent on a record set dated 1918 or later; 1917 itself still warns.

```python
person("Иван Петров")            # before: one field
person("Иван", "Петров")         # after (old-form patronymic)
person("Иван", patr_old="Петров")
```
