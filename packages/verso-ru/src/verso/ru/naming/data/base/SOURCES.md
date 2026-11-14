# The names base: its sources

The three tables here — `names.tsv`, `forms.tsv`, `patronymics.tsv` (the format: `verso.ru.naming.layer_files`) —
are the library's base layer of the names lexicon. They are generated; do not edit them by hand:

    python tools/names_build/build.py

builds them again, byte for byte, from the inputs in `tools/names_build/` of the repository. Every row names its
source in the `source` column, one of a closed list:

| Source | What it is | Licence | Snapshot |
|---|---|---|---|
| `trebnik1906:<line>` | the «Алфавит имён всех святых» of the 1906 Требник, the line of `church_calendar/data/svyatcy_1906.tsv` the name stands on | the 1906 text is in the public domain; the digitisation is © 2018 Slavonic Computing Initiative, MIT (`church_calendar/data/LICENSE.svyatcy`) | slavonic/cu-md-sandbox at 94667d4 |
| `wikidata:Q…` | a Wikidata item of the class «male given name» or «female given name» with a Russian label (`tools/names_build/wikidata-2026-11-08.json`) | CC0 — no attribution required | 2026-11-08 |
| `mk` | a spelling the metric books write, paired with its base (`tools/names_build/corpus_spellings.tsv`) — a name and its base, no record | the maintainer's own | 2026-11-08 |
| `rule` | a form the rules of `verso.ru.naming.forms` give | — | — |
| `editor` | the maintainer's exceptions (`tools/names_build/exceptions.tsv`): the forms the rules do not give, written as grammar, and the few links of the sources that are plainly wrong | the maintainer's own | — |

A `note` beside a row says what else stands behind it: the Wikidata item of a name the books pair (`mk`), or the
maintainer's reason (`editor`).

## How the rows are made

- Every name of the святцы is a canonical name of its sex.
- A Wikidata name the святцы lack is a canonical name of its own, or a variant of a святцы name when its «said to
  be the same as» (P460) links reach exactly one святцы name of its sex. A label that is not one capitalised
  word of the Russian alphabet is left out (Інна, Јелена, Андреј — another language's letters), and so is a label
  that is no given name: a patronymic another name of the base gives (Иванович, Ильич), a man's label that is the
  surname form another man's name gives (Костадинов ← Костадин), and the maintainer's drops (table `drop` of
  `exceptions.tsv`: Кристов, Ленин — surnames). A woman's label that is also a woman's short patronymic (Алина,
  Арина) stays: a woman's «-ина», «-ова» is far more often a name of her own.
- The святцы and the books decide a name's sex as they decide its direction: a Wikidata label of one sex is left
  out where the святцы or the books hold that name in the other sex alone — 20 rows: Борис, Захар, Илья, Данила,
  Иона, Марин, Северин, Фирмин, Кирин, Аника, Калина, Аза, Адриан, Мина, Зина, Инна, Пинна, Римма as women's
  names, Вера and Мария as men's. (Зина, Инна, Пинна, Римма are men's names of the 1906 святцы; the base follows
  them.)
- A spelling of the books is a variant of the святцы name its pairs reach: the books' own pairs first, then every
  link. A chain (Праскова → Прасковья, Прасковья ~ Параскева) is collapsed to its святцы name, so a base is never
  itself a variant. A pair of two святцы names is no variant — the святцы keep both. A spelling whose base no
  source holds is left out: nothing is invented.
- `forms.tsv` holds a form only where the rules give another: a fleeting vowel (Лев → Львович), «-ий» softening
  (Василий → Васильевич), the «-инична» patronymics (Илья → Ильинична), Михаил → Михайлович, «-йло» (Михайло →
  Михайлович) and the short «-ов» of «-ила/-йла» (Гаврилов), the svyatcy's «-ила» names that keep «-ич» (Акила →
  Акилич), Яков → Яковлевич, Иов → Иович, Франц → Францевич, and the foreign women's names that do
  not decline though the rule would (Андреа, Изабель, Николь). An empty cell is the rule's.
- The forms were compared with Russian Wiktionary (kaikki.org extract of 2 November 2026; the comparison only):
  of 1 941 forms compared, 18 differ, each one Wiktionary's own form refused — a slip of the dump, a diminutive
  given its full name's patronymic, a foreign name's other usage.
- An empty forms cell — and a name with no forms row — is the rules': the lexicon reads a base name's forms and
  builds its reverse indexes (short patronymic → father, genitive → name) from them (`Layer.derives`).
- `patronymics.tsv` holds a pin only where the rules give two names one short form: Андрин, Андрина (Андра and
  Андрия), pinned to Андрия (`tools/names_build/exceptions.tsv`, table `patronymics`).

## The maintainer's corrections of the sources

Rows of `tools/names_build/exceptions.tsv`, table `names` (source `editor`, the reason also in the row's `note`):

| Sex | Name | What the sources said | Now | Why |
|---|---|---|---|---|
| F | Алина | a variant of Галина (Wikidata P460) | a name of its own | Wikidata P460 joins two different names |
| F | Гармония | a variant of Ермиония (Wikidata P460) | a name of its own | Wikidata P460 joins two different names |
| F | Линда | a variant of Людмила (Wikidata P460) | a name of its own | Wikidata P460 joins two different names |
| F | Мирлинда | a variant of Людмила (Wikidata P460) | a name of its own | Wikidata P460 joins two different names |
| F | Эрлинда | a variant of Людмила (Wikidata P460) | a name of its own | Wikidata P460 joins two different names |
| F | Эллина | a variant of Елена (Wikidata P460) | a name of its own | Wikidata P460 joins two different names |
| F | Хоуп | a variant of Надежда (Wikidata P460) | a name of its own | a calque, not the same name |
| M | Абель | a variant of Авраам (Wikidata P460) | a name of its own | Wikidata P460 joins two different names |
| M | Владислав | a variant of Владимир (Wikidata P460) | a name of its own | Wikidata P460 joins two different names |
| M | Мирчо | a variant of Владимир (Wikidata P460) | a name of its own | Wikidata P460 joins two different names |
| M | Луций | a variant of Лука (Wikidata P460) | a name of its own | Wikidata P460 joins two different names |
| M | Амадео | a variant of Феофил (Wikidata P460) | a name of its own | a calque, not the same name |
| M | Амадеу | a variant of Феофил (Wikidata P460) | a name of its own | a calque, not the same name |
| M | Амадеус | a variant of Феофил (Wikidata P460) | a name of its own | a calque, not the same name |
| M | Амадеуш | a variant of Феофил (Wikidata P460) | a name of its own | a calque, not the same name |
| M | Амадио | a variant of Феофил (Wikidata P460) | a name of its own | a calque, not the same name |
| M | Амеде | a variant of Феофил (Wikidata P460) | a name of its own | a calque, not the same name |
| M | Амедео | a variant of Феофил (Wikidata P460) | a name of its own | a calque, not the same name |
| M | Богумил | a variant of Феофил (Wikidata P460) | a name of its own | a calque, not the same name |
| M | Готлиб | a variant of Феофил (Wikidata P460) | a name of its own | a calque, not the same name |
| M | Матвей | the books' pairs reach Матфей and Матфий alike | a variant of Матфей | the Russian form of Матфей; the books' pairs reach Матфий (another apostle) too |
| M | Матьфей | through Матвей, Матфей and Матфий alike | a variant of Матфей | a spelling of Матвей, the Russian form of Матфей |

Russian Wiktionary (CC BY-SA) is used only to compare the forms (`tools/names_build/wiktionary_check.py`); nothing
of it is written here.
